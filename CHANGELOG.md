# Changelog

All notable changes to Agent Indigo (formerly *pokemon-agent*) are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions use [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **`tools/ra_sync.py` reads the account's real RetroAchievements unlocks and compares them with the local evaluation (#358).** Read-only: `python tools/ra_sync.py` prints what the account has earned (count, points, hardcore) and what is still locked; `--state x.ss1` also evaluates that emulator state with the agent's own checks and lists where the two differ — earned on the account but not here (a different save, or a wrong check), here but locked there, earned with no check yet, and the partial ('probably') checks that held. The credentials are those of `gen_ra_set.py` (environment or the Keychain item `retroachievements`); the key is never printed, logged or written, errors show the HTTP status only, and nothing of the account's progress is saved to a file (a test pins that). A consistency guard warns when the response's own award count disagrees with the dates parsed, so a changed field name cannot pass as 'nothing earned'. First real read: the account has 0 of 128 (the response says `NumAwardedToUser: 0`).
- **Six more RetroAchievements get checks (#358): 124 of 128 are mapped now.** New readers — `read_game_stat` (gSaveBlock1.gameStats, XOR'd with the encryption key; verified on fixtures: Hall-of-Fame entries 0 before the League, 1 after) and the national dex (`read_dex_owned_national`, `read_dex_owned_count_national`; Johto's Raikou / Entei / Suicune are national 243-245) — back four new check kinds: a game stat reaching a value (the second Champion title = two Hall-of-Fame entries), any of a set of species caught (the roaming beasts), at least n national dex numbers caught ("all 171" — marked *probably*: trades count towards the Pokédex but not towards the achievement), and the Fame Checker holding all 96 entries / every VS Seeker ladder at its top (the readers already existed). Selphy's rescue is `FLAG_HIDE_LOST_CAVE_SELPHY`, set by the 'take me home' scene (read from the decomp's script). Still manual, each with its reason: Selphy's wish (no persistent flag), the Trainer Card machine, triple 7s, Berry Forest's berries.
- **The observation shows RetroAchievements progress (#358).** On the free field after the Pokédex the model sees `Achievements 9/128 (35/781 pts) … quest('achievements') lists what is left and what can still be lost.` once per run, then only the unlocks as they happen — `★ Achievement unlocked (local tracking): 'Title' (+pts). …` (at most three named) — never repeated: it follows the journal count that `main` refreshes every few ticks, like the sweep and rematch lines (`agent.observation._achievement_line`). Unit tests cover the baseline, silence, a named unlock, drift and the three-name cap; a live test reads the baseline from the Misty fixture.
- **The eval harness counts RetroAchievements (#358).** `goals.achievements_at_least(n)` and `achievement_points_at_least(n)` read two new journal fields (`achievements`, `achievement_points`) that `main._apply_progress` refreshes from the game's flags every five decision ticks (the same checks as `quest('achievements')`; an unreadable state keeps the last count). `EpisodeResult` and the scorecard carry them (an `achv` column: `14 (61p)`), and two scenarios use them: `achievements_early` (from the Misty fixture: 20 of the set) and `achievements_post_game_points` (from the Hall of Fame fixture: 450 of 781 points, xfail until the sweeps and Sevii quests are scripted). Local tracking only. Live: the journal count is refreshed from the post-Hall-of-Fame fixture.
- **`quest('achievements')` shows the RetroAchievements checklist against the live game (#358).** `tools/gen_ra_map.py` maps 118 of the 128 achievements by hand to checks the agent can read — a game flag, a trainer's defeat flag, a key item, a badge, a Trainer Tower prize, a species caught, a story beat, or a sweep area's trainers / item balls — every name resolved from the decomp's constants so a typo fails the generation (`knowledge/ra_map.py`); 25 are marked *probably* (the check is necessary but the achievement may need more, e.g. hidden items) and 10 have no check yet, with the reason. `knowledge/ra_progress.py` evaluates them purely; `agent/ra.py` answers the checks from the reader. The call prints `Achievements 9/128 (35/781 pts)`, the missables (they can be lost for good) and what is worth most; `quest('achievements all')` lists everything left, `... done` what is unlocked. Local tracking only — Agent Indigo is not an RA client and nothing unlocks on the website. Live: two fixtures (Misty beaten; after the Hall of Fame) read the expected unlocks.
- **The RetroAchievements set for LeafGreen is imported (#358).** `tools/gen_ra_set.py` reads game 788 from the official Web API (credentials from `RA_USERNAME` / `RA_API_KEY` or the macOS Keychain item `retroachievements`; the key is never printed, logged or written, and goes only to retroachievements.org) into `knowledge/ra_set.py` — public checklist data: 128 achievements, 781 points (21 progression, 24 missable, 1 win condition), as on the set's page; a unit test pins the counts. One finding: the API's `MemAddr` is only an MD5 of each achievement's condition logic, so the set can't drive an rcheevos-style evaluator — each achievement will be mapped by hand to what the agent can check (flags, badges, Pokédex, bag).
- **The FireRed partner's Pokémon know what a wild one of their level knows (#363).** `tools/gen_levelup_learnsets.py` reads the decomp's level-up tables (Kanto 1-151, `knowledge/levelup_learnsets.py`) and `knowledge.movelearn.moves_at(species, level)` replays the game's own initial-moveset rule (level-up moves up to the level, a full set of four dropping the oldest). `make_live_fixtures.py --firered` stages the exclusives with those moves and their real PP instead of Tackle, and the `link_trade` live test checks the traded-for Pokémon arrives at that level with those moves. The two trade live tests now run from a wild encounter on the way by fleeing it and calling the tool again.
- **`link_trade(want, give)` trades for a FireRed-only Pokémon through the Cable Club (#363).** A FireRed core (your FireRed ROM; `FIRERED_ROM_PATH`) is linked to the running game as the partner and the game's own trade runs: one of your Pokémon goes over for Ekans, Oddish, Psyduck, Growlithe, Shellder, Scyther or Electabuzz (the exclusives — `knowledge/exclusives.py`, generated by `tools/gen_exclusives.py` from the decomp's FireRed-vs-LeafGreen wild tables, evolved forms left out). FireRed turned out to share LeafGreen's RAM *and* callback addresses, so `game/link.py` needed no change. The partner states (`saves/partner/partner_firered_1|2.ss1`, five exclusives each at the level they are first found at, Tackle only) are made by `python tools/make_live_fixtures.py --firered` from a FireRed state at a Cable Club counter (`FIRERED_STATE`, default `~/mgba-http/firered_trade_counter.ss0`); nothing is written into the agent's own game to stage a trade. Live: Ekans and Electabuzz (one from each state) arrive in the Pikachu slot and Pikachu stays with the partner; tests skip without the FireRed ROM and state.
- **`Live.warp_to` and dungeon-interior fixture recipes (#279).** The live harness can now stand the player on any map: it writes SaveBlock1's position (+0) and current map (+4/+5) and hands `gMain.callback2` to the game's own map loader (`CB2_MAP_LOAD`, the run a door starts), so objects, tileset and camera load for real — from indoors too, where Fly is refused. `tools/make_live_fixtures.py` uses it for `mt_moon_1f`, `rock_tunnel_1f`, `silph_co_1f` and `victory_road_1f` (previously only play-through `.ss1` files could start inside a dungeon). A live test warps into Mt. Moon, walks with the agent's own `walk_to`, and warps back to the exact tile it left.
- **`trade_evolve` is verified for all four trade evolutions (#363).** The live test is parametrized over Kadabra → Alakazam, Machoke → Machamp, Graveler → Golem and Haunter → Gengar, each through the real Cable Club with the scripted partner; `tests/live/README.md` documents how to generate `saves/partner/` and why live runs boot from a copy of `work.sav`.
- **Live runs boot from a copy of `work.sav`.** The cartridge save is file-backed, so an in-game save — the Cable Club asks "Would you like to save?" before every link-up — overwrote the fixture and later tests booted from the traded party. `tests/live/conftest.py` and `tools/make_live_fixtures.py` now copy it first (and pass the copy to `build_runtime` explicitly).
- **`trade_evolve(pokemon)` evolves Kadabra / Machoke / Graveler / Haunter through the Cable Club with a scripted partner (#363).** `agent/skills/linkpartner.py` travels to the nearest Pokémon Center's 2F counter, restores a partner core from `saves/partner/partner_counter.ss1` (`python tools/make_live_fixtures.py --only partner_counter --out saves/partner`), links it to the running game (`TwoCoreLink.with_partner`) and plays the game's own trade twice — the Pokémon goes over for a throwaway Rattata, evolves on the partner's side (a trade evolution happens on the *receiver*), and comes back — then closes the partner core. The trade screen's cursor is found by a breadth-first search over the decomp's own cursor table (`sCursorMoveDestinations`), because after a trade it restarts on slot 0 and Cancel is reached differently for each party size. Live: Viridian City → Kadabra becomes Alakazam, back upstairs in the Pokémon Center (`tests/live/test_trade_evolve_live.py`). Still to do: a FireRed partner for the version exclusives.
- **A real link-cable trade between two emulated cores: Kadabra → Alakazam (#363).** `game/link.py` now builds each core as a normal `NativeMGBAClient` + reader (so the pair can be driven by the existing skills), and `cable_club_trade(pair)` plays the game's own Cable Club from the Pokémon Center 2F counter: link-up, the seats in the Trade Center, the trade screens, the evolution scene — only buttons are pressed. Two things made it deterministic: both cores run to one shared frame target, and `link_run_keys` holds a core's keys for its *own* first frames (a finished core keeps running until its partner is done, since the partner may be asleep waiting for it mid-transfer). New fixture recipe `cable_club_counter`. Live test: both parties end as Bulbasaur + Alakazam. Still to do: a partner for the main runtime (the second core driven by a scripted routine), a `trade` tool, and a throwaway partner party.
- **Two emulator cores on a virtual link cable — the first step of a trade partner (#363).** `game/_mgba_link_build.py` compiles the host half of libmgba's SIO lockstep against the Homebrew build (no vendored mGBA): a pthread mutex + condition variables behind `mLockstep`'s callbacks, one thread per core, a `wait` that is a *request* honoured between run-loop iterations (as mGBA's own thread layer does — blocking inside the callback deadlocks both cores). `game/link.py` wraps it as `TwoCoreLink(rom)`: `run(frames)` steps both, `frame_counters()`, `sio_modes()`. A live test runs 1,200 frames in twelve runs: no deadlock, equal frame counters, both games in the multi-player link mode. Nothing drives the Cable Club yet; CI builds the module so a Homebrew change to the internal headers is caught.
- **`tools/make_live_fixtures.py` rebuilds live-test fixtures from `work.sav` (#279).** A recipe stages a situation with the harness helpers (Fly, flags, badges, the new `Live.add_mon` that appends a party member — `Addr.PARTY_COUNT` 0x02024029, verified live — and the agent's own `go_to` to walk out of the boot building) and writes the state: `--list`, `--only`, `--force`, `--out`. Three recipes so far (`threemon`, `vermilion`, `league_door`); a live test generates all three into a temp folder, loads them back and checks map, party, badges and key items. Contributors without the play-through `.ss1` files are no longer blocked on those.
- **The island side quests are in the quest log (#360).** Three guide beats read from the decomp's scripts: Berry Forest (rescue Lostelle — `FLAG_RESCUED_LOSTELLE`, an Iapapa Berry; Tri-Pass), Icefall Cave (the Rockets in its back chamber and Lorelei — the rescue scene's flag; Rainbow Pass) and the Tanoby Ruins (the Sevault Canyon key puzzle opens the seven Unown chambers — `FLAG_SYS_UNLOCKED_TANOBY_RUINS`; Rainbow Pass). They show as side quests with their payoffs and gates and tick off by flag; every fight and walk stays the model's.
- **The three Sevii move tutors join `tutor` (#360).** `tools/gen_tutors.py` now reads Explosion (the Hiker beside Mt. Ember's south entrance), Body Slam (Four Island's house) and Swords Dance (Seven Island) from the decomp into `knowledge/tutors.py` (15 tutors), and `tutor` rides the Seagallop to the right island first (`go_to`'s `map:` address for the interiors with no name). Live: a Voltorb learns Explosion from Vermilion, and a Bulbasaur learns Swords Dance on Seven Island (the Rainbow Pass menu's second page) — `tests/live/test_tutor_sevii_live.py`.
- **Moltres' fight starts on the real game (#361).** `tests/live/test_strength_walk_live.py` now carries `quest('moltres')` on from the summit: the next call walks to (9,6) and the one-shot L50 Moltres battle begins (asserted from `gEnemyParty`), so both Sevii legends are exercised end to end up to their battle.
- **`walk_to` solves a Strength boulder puzzle on its own, and Moltres' summit is reachable (#435).** When no walkable path exists and a Pokémon knows Strength, `nav._strength_step` hands the live floor (passable grid, loaded boulders, NPCs, warps) to `knowledge.boulder_puzzle.solve` — the Victory Road solver — makes the first push with the same primitive (face, A, "use Strength?" yes, a 12-frame hold) and lets `walk_to` replan from where the boulder went; an unsolvable floor is remembered so it is not searched again. Mt. Ember's exterior joins its south arrival to the Summit Path door only by clearing two boulders, so `map_graph` has a hand hop (`_patch_mt_ember`) onto the far side (16,46); `route_to` now plans arrival → boulders → Summit Path 1F-3F → exterior → summit. Live: `quest('moltres')` from Vermilion reaches Mt. Ember's summit (`tests/live/test_strength_walk_live.py`).
- **The slot stop-loss path is tested on the real game (#359).** With `MAX_SLOT_LOSS` pulled down to 0 the session ends as soon as it is behind its start (measured: 2 spins, "Stopped early: the stop-loss (0 coins) was reached"), and a purse with less than one bet ends it without spinning, control back on the field.
- **`quest('trainer_tower <single|double|knockout|mixed>')` runs a Trainer Tower challenge (#369).** From the decomp: stepping onto the lobby's trigger tile (9,7) while `VAR_MAP_SCENE_TRAINER_TOWER` is 0 plays the receptionist's scene (YES / NO / INFO, then the four challenges); floors 1F-8F share one shape — the stairs up are the warp at (15,6) — and the Roof's Owner at (9,7) gives the prize (`trainerTower[type].receivedPrize`). The driver goes to Seven Island by the Seagallop when needed, answers the scene, climbs floor by floor and talks to the Owner; every trainer battle is handed back to the model (a Tower fight cannot be fled) and the next call continues from the floor you are on. A live test wins a whole Single challenge on the real game (a lone Pokémon boosted to outlast the L100 teams). The Double / Knockout / Mixed party rules are not modelled: the call starts them and the game enforces them.
- **`quest('moltres')` and `quest('mewtwo')` (#361).** The one-shot legendary protocol of the Zapdos / Articuno drivers: gate on the story (the Sevii visit for Moltres, the linked Network Machine for Mewtwo), travel in (Moltres: the Seagallop to One Island is taken automatically from the mainland), walk up to the Pokémon and hand the fight to the model with the usual "catch it, never knock it out" briefing. Moltres is on Mt. Ember's summit (1,101) at (9,6), Mewtwo on Cerulean Cave B1F (1,74) at (7,12). Reaching Mt. Ember's exterior is verified live; the walker cannot yet get from it to the summit, nor to Cerulean Cave's door — both filed as issues. The map-to-island table of `knowledge/ferry.py` now comes from every Sevii map folder of the decomp (the first guess by map group missed the outdoor maps).
- **`quest('ferry <island>')` rides the Seagallop (#360).** `knowledge/ferry.py` holds the decomp's menus (`seagallop.inc`, `DrawSeagallopDestinationMenu`): with the Rainbow Pass one drawn list in two pages (page 0 the first four of Vermilion / One / Two / Three / Four minus where you stand, then OTHER; page 1 the three far islands), with the Tri-Pass the short lists for One-Three Island. The driver goes to Vermilion's pier (or the Harbor of the island you are on), talks to the sailor, moves the cursor to the island asked for and lets the crossing play; it reads which pass you have from the Celio-chain var and says what is missing. Verified by the map you arrive on. Live tests: Vermilion → Three Island (Tri-Pass), Vermilion → Five Island (Rainbow Pass, second page), Five → Seven → Vermilion.
- **LeafGreen's two Nidoran trades join `quest('trade')` (#362).** Read from the decomp's version branch of `ingame_trades.h`: MR. NIDO (a Nidoran M) from the Underground Path's Route 5 entrance house for a Nidoran F (`FLAG_DID_MS_NIDO_TRADE` 0x24B), and NINO (a Nidorino) from the Route 11 gatehouse's 2F for a Nidorina (0x251) — FireRed's are the mirror image, which is why they were left out before. A live test trades a Nidoran F for MR. NIDO from Vermilion.
- **`quest('safari <species>')` hunts one Safari Zone species (#362).** `knowledge/safari.py` reads the decomp's encounter tables (the Safari's four areas, grass rows only). `quest('safari')` lists what can be hunted and where (Chansey: Center / North, Tauros: North / West, Kangaskhan, Pinsir, Rhyhorn, …); with a species the driver pays the ¥500 and walks in if you are outside, travels to the nearest area where it lives without walking out of the exit, and paces on the tall grass until a wild Pokémon appears. The call then ends and says whether it is the target (★), how many Safari Balls and steps are left, and that the model plays the turns with `safari('ball' | 'bait' | 'rock' | 'run')`; calling again carries on from inside (no second fee), and a visit that ran out of steps or balls is reported.
- **The Game Corner economy is tested end to end on the real game (#359).** One live test buys coins with yen (¥20 each, in lots of 50), plays a stretch of spins and buys an Abra at the prize counter, reading every step back from the game: the yen and coins add up exactly, the Abra joins the party, and control is back on the field.
- **Last-chance warnings for trainers that vanish (#366).** The generator now records, per area, the trainers whose map object carries a `FLAG_HIDE_*` that a story script sets (`vanish`). Two events are verified in the decomp: beating Giovanni in the Viridian Gym sets `FLAG_HIDE_MISC_KANTO_ROCKETS` (the 11 Rocket Hideout trainers and 4 Rocket Grunts on Mt. Moon's B2F go home), and beating the Rocket Admin in Five Island's warehouse sets `FLAG_HIDE_FIVE_ISLAND_ROCKETS` (8 trainers on Five Island, 1 on Outcast Island). `quest()`'s area listing and `quest('sweep <area>')` say how many of them are still unbeaten and what the event is — advice, never a wall — and stop once the event has happened or they are all beaten.
- **The Sevii Islands and Cerulean Cave are sweep areas (#360, #366).** `tools/gen_area_sweeps.py` now groups the islands' maps the way the completion checklist names them — Kindle Road / Mt. Ember (16 trainers, 6 items), Two-Three Island with Cape Brink, Bond Bridge and Berry Forest (6 / 5), Four Island / Icefall Cave (0 / 6), the Five (22 / 12), Six (29 / 6) and Seven Island (16 / 4) regions, and Cerulean Cave (0 / 8) — so `quest('sweep <area>')` and the progress lines cover them. The Icefall Cave grunts and the Trainer Tower's trainers are scripted / built at run time rather than object events and are not counted.
- **`quest('mt_moon_fossil helix|dome')` (#362).** Mt. Moon B2F's two fossils are a one-time either-or (`FLAG_GOT_FOSSIL_FROM_MT_MOON` 0x232; the Super Nerd takes the other), so the pick is the model's: without a choice the call explains both lines and takes nothing. With one it travels to B2F (`map:1,3`), stands below the chosen fossil — Dome (13,7) or Helix (14,7) — takes it and verifies by the flag; trainer fights on the way are handed back. A side-quest entry and the dex plan point at it; `quest('fossil')` revives it at Cinnabar.
- **`quest('fossil [helix|dome|amber]')` revives a fossil at the Cinnabar Lab (#362).** A resumable driver for the decomp's three-stage revival: hand the fossil over (the scientist wanders, so the driver walks to where he stands now; his list shows a Mt. Moon fossil first and the Old Amber second, and the cursor is moved to the one asked for), walk out through the Lab's entrance map and back (that moves `VAR_..._REVIVE_STATE` to 2), then talk to him again for the level 5 Omanyte / Kabuto / Aerodactyl (party or PC; the nickname box is declined); verified by `FLAG_REVIVED_*`. The Helix / Dome either-or at Mt. Moon is still the model's.
- **`quest('old_amber')` (#362).** The Pewter Museum scientist at (21,3) gives the Old Amber free. The decomp's layout matters: he stands in the museum's right half, reached by the building's SECOND door (Pewter City (25,4), behind a Cut tree) — the left door only leads to the ¥50 ticket counter and the fossils — so the driver goes round to that door (and says `quest('cut')` first when nobody can Cut). A side-quest entry and the dex plan's Aerodactyl line point at it; the Cinnabar revival is not driven yet.
- **The slot driver's edge is measured on the real game (#359).** A live test runs 60 spins at a full bet and asserts the session comes out ahead (measured +14.4 coins a spin over 60 spins, three jackpots, against the issue's ~+16), stays above the stop-loss, and that a nearly full Coin Case never goes past `MAX_COINS`.
- **`quest('trade <species>')` — the in-game NPC trades (#362).** `knowledge/trades.py` (from `ingame_trades.h` and each trader's map script) holds the seven Kanto trades that do not depend on the game version — Farfetch'd, Seel, Electrode, Lickitung, Tangela, Mr. Mime, Jynx — with the map, the NPC's tile and the `FLAG_DID_*_TRADE`. The driver checks the party owns the wanted species, travels to the trader, talks, answers YES, picks the wanted Pokémon on the party screen and verifies by the flag; `quest('trade')` lists them with the done ones marked. The model chooses which trade and which spare. (The two Nidoran trades differ between FireRed and LeafGreen and are not covered.)
- **`quest('eevee')` (#362).** The free level 25 Eevee in the little room above Celadon Mansion (`FLAG_GOT_EEVEE` 0x263): the driver travels there (`map:10,11`), faces the ball at (7,3), takes it and declines the nickname; a full party sends it to the PC by the game's own script. A side-quest entry and the dex plan point at it.
- **`quest('sweep <area>')` (#366).** The driver for the area sweeps: it reads what is left from the game's flags and walks it — item balls first (the safe ones), then the trainers — travelling between the area's maps, picking balls up and walking up to each trainer; every battle is handed back to the model (the call ends, `quest('sweep …')` again resumes, the flags say where it stands) and a hurt lead stops it before the next trainer. Unreachable targets are skipped with a note. `tools/gen_area_sweeps.py` now also records where every trainer and ball stands. Hidden items are left to the Itemfinder / `pick_up_items`.
- **`quest('rematch')` — the VS Seeker loop (#367).** Charges the battery (the item counts 100 steps while it is in the Bag, read from SaveBlock1), uses it from the Bag, then walks up to every trainer the game flags for a rematch on the map (the table at SaveBlock1+0x63A, indexed by the NPC's localId) and hands each battle to the model; calling it again resumes, and it stops on a hurt lead. New readers `read_vs_seeker` / `read_objects_by_local`; `quest('rematch status')` reports the charge and who is flagged. The decomp facts it relies on: a use flags each beaten trainer in view with a 70 % chance, the flags are withdrawn after 100 more steps or on leaving the map, and a trainer whose ladder has a single rung can never be flagged.
- **Fame Checker progress and a talk driver (#368).** `tools/gen_fame_checker.py` generates `knowledge/fame_checker_data.py` from the decomp: all 96 entries (16 people x 6), each with the script that sets it, the NPC / sign / scene it comes from and its tile, the hide flag of its NPC (the magazine journals only come out after that Gym leader, the gossipers after the Hall of Fame) and the game-clear gate of the aides. `read_fame_checker()` reads `gSaveBlock1.fameChecker`; `quest('fame')` lists every missing entry by person with what it waits for, and `quest('fame go')` walks to the nearest open NPC / sign (this map first, then by route length), reads it and checks the game's own bit; battles hand control back and the call resumes. Entries set by a battle or a cutscene are listed, not driven.
- **The Sevii chain in the side-quest log (#360, phase 0/2 start).** Four flag-checked entries from the decomp's scripts: One Island (Bill's forced sail after Blaine, Celio, the Tri-Pass — `FLAG_WORLD_MAP_ONE_ISLAND`), the Ruby from Mt. Ember (needs the National Pokédex; `FLAG_GOT_RUBY`, then the Rainbow Pass), the Sapphire from Five Island's warehouse (`FLAG_RECOVERED_SAPPHIRE`) and the linked Network Machine (`FLAG_SYS_CAN_LINK_WITH_RS`: Cerulean Cave, the roamer and the top rematch teams open). Information only; the ferry driver is not written yet.
- **Moltres and Mewtwo in the side-quest log (#361, information part).** Two flag-checked entries (`FLAG_FOUGHT_MOLTRES` / `FLAG_FOUGHT_MEWTWO`) behind the Sevii chain, with the roaming beast the Network Machine starts (Raikou for Squirtle, Entei for Bulbasaur, Suicune for Charmander, level 50 — read from `GetRoamerSpecies`).
- **The second League run (#369).** After the Hall of Fame with the Network Machine linked (`FLAG_SYS_CAN_LINK_WITH_RS`), `quest('elite_four')` no longer says "Rematches are not scripted": the game resets the rooms' defeated flags every time the Hall of Fame is entered (`EventScript_ResetEliteFour`), so the existing room walker runs the rematch teams unchanged (Lorelei L63-66, Bruno L65-68, Agatha L65-70, Lance L66-72, the Champion L72-75, from `trainer_parties.h`). The readiness bar for that run is its own (`REMATCH_KEY`: best Pokémon L72, five at L63+, 14 heals, 5 Revives; a warning once, not the first run's level wall — a loss only costs time once the game is cleared), the finish records a `league_rematch` milestone, and without the link the call points at `quest('network_machine')`.
- **Trainer Tower progress and a side-quest entry (#369, information part).** `read_trainer_tower()` decodes the four challenge records (Single, Double, Knockout, Mixed) from `gSaveBlock1.trainerTower` (the Owner's prize = the challenge is won), a new `("tower", n)` done-spec marks the beat done when the first n prizes are in, and the post-game side-quest `trainer_tower` explains the Time Attack (eight floors, the clock, trainer levels equal to your best Pokémon's, no Exp or money). The lobby, clock and floor walks are not driven yet.
- **The Prize Corner priced in time (#359).** `game_corner('status')` now lists every prize, cheapest first: coins, how many more you need, what that costs at the slot driver's measured rate (about +16 coins a spin, ~700 frames a spin: "≈ 269 slot spins, ~52 min of game time"), and what the prize is for — a new Pokédex entry or not, which party members can learn each TM, the held item's effect (from the decomp's descriptions). Information only; nothing is ever bought or recommended.
- **A Pokédex view (#362).** `quest('dex')` shows the Kanto Pokédex: caught / seen / missing, and every missing species grouped by whether it can be had here now, only after another catch (an evolution whose pre-evolution is not owned yet), only with a trade partner (a trade evolution or a version exclusive) or only as an event (Mew), each with its best source and the quest that does it. The `quest()` listing points to it.
- **VS Seeker rematch progress, read from the game's flags (#367).** `tools/gen_rematches.py` reads the decomp's rematch table (221 rematchable trainers, each with a ladder of up to six parties — every party its own trainer id and so its own defeat flag — and the story flag that opens each rung: the VS Seeker, the Celadon and Fuchsia visits, the Hall of Fame, the Sevii Network Machine) into `knowledge/rematch_data.py`; `knowledge/rematches.py` counts where every ladder stands. Once the VS Seeker is owned the observation shows `REMATCHES: 12/221 trainers at their top team · 31 have a rematch ready · 20 wait for the Hall of Fame …` when it changes, and the VS Seeker (the woman in Vermilion's Pokémon Center) is a side quest with its payoff. Using the item and walking the ready trainers (`vs_seeker` / `rematch` drivers) are a separate step.
- **`RUN_GOAL=completion` and a post-game briefing (#357).** By default a run still ends at the Hall of Fame; with `RUN_GOAL=completion` it keeps going until the completion target — the Kanto Pokédex (151 caught) and every side quest — or a budget ends it. After the Hall of Fame the observation shows what is left, ordered by availability and never forced (dex count, side quests open, what the National Pokédex needs: 60 caught + the Sevii Islands reached + a talk with Prof. Oak, and honestly that the Sevii/legendaries/roamers are not scripted yet), the
  system prompt says the game is cleared, `quest()` gets a populated POST-GAME section (`national_dex`), `national_dex` is recorded as a milestone when the game enables it, and the run's end record / eval scorecard carry `post_game_steps` and `dex_owned`. New eval scenario `post_game_national_dex` (from `post_hof.ss1`, an xfail until the Sevii work lands).
- **A side-quest log (#356).** `quest()` now lists MAIN (the road to the Elite Four), SIDE QUESTS available now — each with what it is worth (TM28 Dig, the Old Rod, a legendary …) — and those not open yet with why (the Oak's Aide counts, a missing story step), plus what is done. When the set of open side quests changes the
  observation says so once (`SIDE QUESTS you can do now …`), and `quest('elite_four')`'s prep notes how many are still open before the Hall of Fame: advice, never a wall, and the either/or choices (Hitmonlee / Hitmonchan) stay the model's. `Beat` gains `tier`, `gate` and `payoff`; a unit test pins the gates to the Aide thresholds, a live test runs it from the Misty fixture.
- **Area completion, read from the game's own flags (#366).** `tools/gen_area_sweeps.py` reads the pret/pokefirered decomp (every trainer's `trainerbattle_*` → defeat flag, every item ball's `FLAG_HIDE_*`, every non-renewable hidden item) and writes `knowledge/area_sweeps.py`: 26 named areas (Viridian Forest, Mt. Moon, Rock Tunnel, the S.S. Anne, Rocket Hideout, Pokémon Tower, Silph Co., the Mansion, the Power Plant, Seafoam, the Safari Zone, Victory Road, the gyms, the route groups). `knowledge/sweeps.py` counts progress per area (story-conditional item balls and respawning mushrooms are left out), and the observation shows `AREA PROGRESS: Mt. Moon: 4/11 trainers, 1/10 items, …` when it changes; `quest()` lists the started-but-unfinished areas. The one area that is lost by moving on, the S.S. Anne (it sails once you have HM01 Cut), says what would be missed — advice, never a wall. A `sweep(area)` driver is a separate step.

### Changed
- **The README is rewritten, with the new banner.** It now covers what the project does today — 43 tools, 54 quest beats, the side quests / area sweeps / post-game / RetroAchievements tracking, the trade partner (`trade_evolve`, `link_trade`), and testing without a model (1,366 unit tests, the 224-test live suite that gates merges, the scripted end-to-end run) — with the quickstart, the tool table, the documentation index and the project layout brought up to date. The banner is the new wordmark, with a transparent background so it reads on GitHub's light and dark themes.

### Fixed
- **The scripted full-chain run clears the Hall of Fame again — a model-free end-to-end regression (#279).** Since the Level wall made the Elite Four un-skippable, `tools/scripted_run.py --chain` stalled in two minutes. Three harness fixes: its progress check now counts the party's experience (`read_party_exp`, in 1,000-point steps) so a grind toward the L46 bar is progress; a `heal()` refused in the sealed League rooms means 'press on' instead of a 40-call loop; and a no-grass `grind()` (the Plateau has none) makes it ignore the 'train first' advisory and call the quest again. The run also boots from a copy of the battery save now, so an in-game save cannot overwrite the real one. Reference run from `route23_stuck`: passed, 1,937 steps, 5 blackouts, 41 minutes (`docs/live-ci.md`).
- **CI's macOS binding job imports libmgba again (#446).** Homebrew's `mgba` bottle names ffmpeg 8's libraries while the runner has ffmpeg 9.1, so `import game._mgba_native` failed and `tests/test_binding.py` quietly skipped (`1 passed, 5 skipped`) — the job only proved the extensions compile. A new step symlinks every missing `libav*`/`libsw*` path libmgba names to the installed copy of the same library (it prints what it saw), a following step imports both compiled extensions so a broken import fails the job instead of skipping, and the binding tests now report `3 passed, 4 skipped` (the four ROM tests, as intended).
- **Leaving the Trade Center survives a missed button (#363).** After one live-suite run the cancel step of `game/link.py` left both cores on the trade screen (the in-game save before the link-up takes a different time depending on the flash the shared runtime starts from, so a fixed-timing press can miss its window). `leave_trade_room` now presses A for any core still on the screen every ~5 s of waiting — it opens the 'Cancel trade?' prompt or answers YES, and a core that has already left is left alone. Checked by dropping the YES press on purpose: the nudge alone finishes the cancel.
- **`quest('mewtwo')` reaches Mewtwo (#436).** Cerulean City's cave door is on a beach that no land touches: x 4-6 beside it is a lake and x 7 a wall (the raw map data: elevation-1 metatiles), and the lake is the same water as Route 24's river across the map seam. The generated regions model water inside one map only, so the planner's only answer came from its optimistic fallback (a direct warp it could not walk). `knowledge/map_graph.py` now has the hand link — Cerulean → Route 24's west bank → Surf into the river → across the seam on the water → the beach → the door — and the whole trip is checked on the real game (a Route 24 trainer, the river, the cave's own Surf and ladders, Cerulean Cave B1F, Mewtwo L70). The legend briefing also reports the real level instead of a fixed L50.
- **Surf no longer recurses until the stack ends (#361).** A shore walk with no path started Surf again, which walked to a shore again … (a `RecursionError` found on Kindle Road). A running Surf attempt now refuses to start a second one (`_surf_active`).
- **`quest('sweep Mt. Moon')` now collects all ten balls (#428).** Three separate problems hid behind "couldn't reach the item": (1) a wild battle that ended the walk was recorded as "unreachable" and the ball skipped for the whole call — a battle is now handed to the model and the ball stays open; (2) each call re-picked the nearest target from wherever the fight left it, so the sweep oscillated between the two ends of B2F — the target is now kept across calls (`_sweep_goal`); (3) B2F's corner rooms are reached only by a ladder from a floor that is itself split into regions — the driver now routes over the region graph (`knowledge.map_graph.route_to` with the target's `node_for`) from the region it is in to the target's, one warp at a time. The live test went from 7 of 10 to 10 of 10 (it fights a Rocket on B2F with the lead's moves and uses a Repel so the measurement is the walk, not the encounter rate).
- **`map_epoch` no longer depends on how often the map is polled (#391).** The emulator client counts the game's own warp-loads (the edges of `gMain.callback2` into the map-load callback, `Addr.CB2_MAP_LOAD`, sampled on every frame) and the reader's `map_epoch` is built from that, so leaving a floor and re-entering it between two calls is never missed (Victory Road's boulder memory relies on it). A battle return is not counted; a live test pins both.
- **A warp is never read as a menu (#402).** `MENU_OPEN` stays set (not even 0/1 — it was seen as 252) after any menu closes, so every later warp's fade read as `IN_MENU` and `go_to` / `go_to_map` reported "Interrupted while walking to the East edge (context IN_MENU)" (9 watched runs, mostly at Pewter's east edge, where a Pokémon Center heal had left the byte set). The map-load callbacks are now always `TRANSITIONING`, and on the field callback a menu-byte + fade counts as a menu unless a warp task (and no Start-menu task) is running in gTasks. Verified frame by frame on the real core; a golden-vector test and a live test pin it.
- **LLM failures are told apart (#372).** A *context overflow* (HTTP 400, "context size exceeded") used to roll the history back and send the identical request 30 times until `error_budget`; it now shrinks and resends
  (images → older turns → the observation cut to 2.5k chars) and remembers a prompt ceiling so the next request fits. New `CONTEXT_TOKENS` fits the history by *estimated tokens* (calibrated against the server's `prompt_tokens`),
  not just message count. *Fatal* errors — a quota/billing 429 (previously "transient": ~2 h of backoff), 401/402/403, 404 unknown model — raise `LLMFatalError` and end the run at once with `reason="llm_error"`; `Retry-After` is honoured.
  A failure on a later round of a step keeps the completed rounds' messages (their tool calls already moved the game) instead of deleting them.
- **No `continue` path skips the run caps any more (#373).** The blackout recovery used to `continue` past `MAX_WALL_SECONDS` / `max_steps` / the spend caps, so a whiteout that never recovered tapped A forever. `_guard_stop` now runs at the top
  of every loop iteration and after each decision; the recovery gives up as `stalled` after `MAX_BLACKOUT_PASSES` (40) passes (saving a stall state under the run's `stalls/`), and "the party is wiped" is confirmed with a fresh, fallback-free
  read (`LeafGreenReader.read_party_fresh`) instead of a possibly stale last-good party. A failing `read_state` inside an exit path no longer masks the exit reason.
- **Reasoning is never replayed into history (#374).** `<think>` blocks were only stripped when `ENABLE_THINKING=true` (default false) and an unclosed block (a reply cut off by `MAX_TOKENS` mid-thought) never was, so a Qwen3-style
  model re-sent its thoughts every turn — context pressure and the 400 the code comments warn about. `agent.history.split_think` now removes closed, unclosed and implicit-open blocks regardless of the flag, `reasoning_content` /
  `reasoning` fields are read too, and `ENABLE_THINKING` only decides whether the thinking is shown / logged. A reply that ends on `finish_reason="length"` is reported and leaves a well-formed turn.
- **The "RAM writes are menu cursors only" rule is enforced (#375).** `NativeMGBAClient.write8/16/32` check `game/write_guard.py`'s allow-list — `gMoveSelectionCursor`, `gActionSelectionCursor`, the `sShopData.itemList` scratch pointer and the SaveBlock2
  battle-style option (through the live pointer) — and raise `WriteNotAllowed` for anything else (party, bag, RNG, saves…). `tests/live` opts out with `client.unrestricted_writes = True`; a test scans the source so a new write site must be
  registered.
- **"Unreadable" no longer reads as zero (#376).** While the SaveBlock pointers are invalid (title screen, reset, a transition frame) `read_flag`, `read_var`, `read_money`, `read_coins`, `read_bag`, the item/TM pockets, the key-item readers and the Pokédex readers
  return their last good value (like `read_badges` always did) instead of `False` / `0` / `{}` — which had produced phantom "key item obtained" events and "restock" nags. A failed money/coin decrypt is no longer "no money". `LeafGreenReader.reset_caches()`
  forgets every last-good value and is called by the `load_state` tool and after a power cycle, so a value from the old timeline never answers for the new one.
- **Party validity is the game's own checksum (#377).** A party slot used to be judged by loose range checks, and one implausible slot froze the whole party view on an old snapshot (hiding level-ups and HP changes in every other slot). `checksum_ok` verifies the Gen III
  checksum (`+0x1C` over the decrypted data) and the Bad-Egg flag; `PokemonStatus` gains `valid` / `is_egg` / `stale`; only the bad slot falls back to its last good read, for at most `STALE_READS` (3) reads, after which it is shown as it is (`valid=False`).
  A live test confirms every occupied slot of all 33 saved scenes (battles included) passes the checksum.
- **`record_milestone` is checked against the game (#379).** A milestone the cartridge can confirm (`got_cut`/`got_surf`/… via the story chain's flags, `got_silph_scope`/`got_poke_flute` via key items, `beat_*` via the badge byte, `starter_chosen`, `delivered_oaks_parcel`)
  is only recorded when the game agrees, otherwise the tool says what it checked. Hand-recorded milestones are tracked (`model_milestones`) and startup drops any the loaded save contradicts; the two with no RAM signal (`cleared_rock_tunnel`, `woke_snorlax_16`) are accepted and marked "taken on your word".
- **Run artefacts are written atomically and the exit status says why a run stopped (#382).** `meta.json`, the checkpoint pointer `latest.json` and the journal snapshots go through `memory/atomic.py` (temp file + fsync + rename), so a crash leaves the previous file instead of a truncated one
  (a truncated `latest.json` made `RESUME=latest` silently pick an older checkpoint). A checkpoint whose snapshot or pointer write fails no longer leaves an orphan `.ss1`; battle-journal rows are one whole-line write. `python main.py` exits 0 for the goal or a requested cap
  (`MAX_STEPS`, `MAX_LLM_CALLS`, `TOKEN_BUDGET`, `MAX_WALL_SECONDS`), 1 when the run broke (`stalled`, `error_budget`, `llm_error`), 130 on Ctrl-C (2 = could not start).
- **`LOAD_FLAGS` is documented and pinned (#380).** The binding's comment said "everything except screenshot" but the value (29) leaves `SAVEDATA` out. Verified live that this is the wanted behaviour — with a battery save loaded, `load_state` rewinds RAM only and a power cycle still "Continues" from the `.sav`; with none loaded the state supplies the save — so the comment, `CLAUDE.md`, a unit test on the constant and a live regression test now say so.
- **The emulator binding fails loudly and cleans up (#381).** `screenshot()` returns whether the core wrote the frame (a failed write used to leave the previous PNG to be read back and sent to the model as the current frame); the model's screenshot is now encoded in memory
  (`framebuffer_png`, verified pixel-identical to libmgba's own PNG) with no disk round-trip. Keys are released when the frame watchdog trips mid-press (idle detection keeps its sparse fingerprint on purpose: a whole-frame hash is never idle in battle);
  state files are written beside their target and renamed into place; `read_range` is capped at 1 MiB; `NativeMGBAClient.close()` / `with` free the core deterministically (and the C side checks its allocations and deinitialises the core config).
- **The eval harness can gate and its numbers are comparable (#378).** `python -m evals` exits 0 / 1 (a scenario FAILED) / 2 (unknown scenario) / 3 (`--strict` and something was SKIPPED or nothing ran); a scenario whose goal is already met at the start, or whose emulator is unavailable, is SKIPPED instead of passing at step 0 or being dropped.
  Every result carries a `meta` block (model, temperature, `MAX_TOKENS`, vision, git SHA, ROM and fixture SHA-1, Python), `--trials N` reports a pass rate, `python -m evals <name>` works, each scenario's emulator is closed. `stuck_ratio` now counts only the ticks after a movement tool and compares the map as well as the tile. The default start save is the stable `saves/live/work.sav`
  (the maintainer's moving play save made every scenario meaningless once it was past Brock). `tests/test_nav_scenarios.py` gets a fresh emulator and scratch journals per test, flees wild battles like the model would, and fails loudly on a trainer instead of skipping (the Pewter case is a strict xfail with its reason).
- **A start point that will not load now stops the run (#370).** `build_runtime` raises `StartPointError` when `START_FROM_STATE`, `START_FROM_SAVE` or `RESUME` names a file that is missing or that libmgba rejects, instead
  of printing a (quiet-mode: nothing) warning and playing from the power-on screen. `python main.py` prints the reason and exits 2. The eval harness checks each scenario's fixtures first and reports
  `SKIPPED (fixture_missing: …)` / `SKIPPED (start_point_failed: …)` without booting an emulator; `python -m evals --list` marks missing fixtures and `--strict` exits 1 when anything was skipped.
- **Long-term memory no longer forgets four of its own keys on reload (#371).** `gym_losses` (a loss inside a gym blocks `challenge_leader` until the team grows), `hidden_taken`, `pc_visited` and
  `shop_broke_at` were written to `progress.json` but dropped by `LongTermMemory._load` because they were missing from `DEFAULTS`. They are declared now, and `_load` keeps any undeclared key
  (only `RETIRED_KEYS` are dropped). A test scans the source for every `ltm.data` key and fails if one is not in `DEFAULTS`.

### Changed — the model makes the choices code used to make
- **Names.** `quest('new_game')` with nothing chosen (and no `STARTER` / `PLAYER_NAME` / `RIVAL_NAME` in `.env`) presses no button and asks the model to pick its starter, its name and its rival's name; with
  the choices it plays the intro. The starter's and the Silph Co. Lapras's "Give a nickname?" boxes are handed back to the model (`answer_prompt('yes')` then `enter_name(...)`, or `'no'`) instead of
  being declined; the quests resume afterwards. `new_game defaults` and `nonick` keep scripted runs and tests working, and a value set in `.env` still decides for the model. **Remove those three lines from your `.env` to let the model choose.**
- **No fixed Pokémon picks.** Removed the table that named a counter per gym (Diglett for Surge …) with where to find it, the HM "catch one that can: …" lists, the catch-policy bonus for those species,
  and every hard-coded species suggestion in the prompts and hints (Bulbasaur's Vine Whip for Brock/Misty, "catch a Diglett", "Pidgey / Spearow lines" for Fly, teach Dig to Diglett/Sandshrew …). The team
  report and readiness now state the NEED (types the leader is weak to, which HM nobody can learn, what the PC already holds) and leave who to catch, bring or box to the model.
- `quest('hitmon')` no longer always takes Hitmonchan: `quest('hitmon lee')` or `quest('hitmon chan')` — the model chooses.

### Changed — the project is now Agent Indigo
The repository is renamed **Agent Indigo** (`agent-indigo`; it was `pokemon-agent`) and the documentation is rebuilt from the ground up.
- New README with the project banner (`docs/assets/agent-indigo.png`): what it is, why the model/skill split exists, a quickstart, the tool areas, how to watch / resume / measure runs, responsible use and acknowledgements.
- New `docs/`: getting started, architecture, configuration (every environment variable), tools (generated; a test keeps it current alongside `CLAUDE.md`), models, memory/journals/logs, testing, plus a docs index.
  `HISTORY.md` is split into `docs/reference/` (Gen III data structures, game knowledge, the community RAM map) and `docs/archive/mgba-http.md` (the retired backend).
- `CONTRIBUTING.md`; `CLAUDE.md` retitled and its machine-specific paths and links updated; `pyproject.toml`, the viewer caption, the startup banner and the screenshot temp-dir prefix use the new name.
- `python tools/gen_tool_docs.py` now regenerates both `CLAUDE.md` and `docs/tools.md`.
- The GitHub repository was renamed (old URLs redirect); the local checkout directory is independent of the name.

### Removed — the legacy mGBA-http backend
The agent has run on the in-process libmgba binding since v0.x; the HTTP transport (mGBA GUI + Lua socket + mGBA-http .NET server) had no tests, no CI job and no support for checkpoints, screenshots,
the watchdog, Running Shoes or the viewer, so it only worked as a degraded mode.
- Deleted `game/mgba_client.py` (`MGBAClient`) and the `requests` dependency; `main.build_runtime` always builds `NativeMGBAClient` (the `backend=` argument is gone).
- Removed `MGBA_BACKEND`, `MGBA_HTTP_BASE` and `BUTTON_TAP_DELAY` (only the HTTP client used it) from `config.py` / `.env.example`; a stray `MGBA_BACKEND=` in an existing `.env` is ignored.
- README / CLAUDE.md lose the legacy startup steps and endpoint cheat-sheet; the API reference stays in HISTORY.md, marked retired. `ROM_PATH` still defaults to `~/mgba-http/…` (the folder name is
  historical — where the ROM and save live).

### Added — one journal per save / state
Loading a save used to pick up the ONE global journal (`logs/progress.json` + `logs/battles.jsonl`): a badge-1 fixture arrived with Misty, Surge, Cut, Celadon and 678 battles from the newest
run, and "past losses" lessons leaked between playthroughs.
- `memory/journals.py`: `START_FROM_SAVE` / `START_FROM_STATE` select `logs/journals/<save>-<hash>/{progress.json,battles.jsonl}`; a run's checkpoints share `run-<timestamp>`. `PER_SAVE_JOURNALS=false`
  restores the single global journal; a new game and explicit `ltm_path`/`journal_path` (the eval harness) are unchanged.
- A journal that does not exist yet is DERIVED from the cartridge (the starter and Oak's parcel once a badge is earned, every Fly-flagged town, the badge milestones from the startup reconciliation) instead of copied from another run.
- Every checkpoint writes the journal beside its state (`<ckpt>.ss1.ltm.json` / `.battles.jsonl`, removed with a pruned checkpoint); `RESUME` restores exactly what was true when that state was saved.
- `python -m tools.reset_journal --source <save>` resets one save's journal.

### Fixed — harness advice that sent the model into refusals (DeepSeek watched runs)
- A trapped Pokémon (Wrap/Bind/Mean Look) was told "Better matchup: switch…" and "Options: switch_pokemon…" in the same observation as "you CANNOT switch" — six failed switches in one run. Switch/flee
  advice is now withheld while trapped (`low_hp_advice(trapped=…)`, `better_matchup`, the backup-teammates hint).
- A battle that began mid-trip (a trainer on the way to a Pokémon Center, an encounter while grinding) handed the model a message without saying who leads, so it used the last fighter's moves on the
  lead (15 "'Vine Whip' is not a known move" refusals in one run). The hand-off now names the lead and its moves, and the refusal says who is on the field and which benched teammate knows the move.

### Changed — quality over a full party of six
The prompt said "Aim for a full party of 6 with different types", and the catch policy took any near-level line that "adds a new type", so watched teams filled slots with filler (Wigglytuff, Raichu, a
Pidgeot…) whose XP was then split six ways.
- System prompt: six is a ceiling, not a goal; a strong 4-5 beats six diluted ones; the model is told it is FREE to restructure the party at any time (`pc('swap'|'deposit'|'withdraw')`, an empty slot is
  fine, `team_report()` / `pc('list', detail=true)` to decide), and to box members that aren't pulling their weight instead of grinding them up. The "level the whole team" step now says to level the team that fights.
- `catch_policy.evaluate`: from a core of four (`CORE_SIZE`) a catch must strengthen the team — a premium line, an upgrade over the weakest line, a team gap (`wanted`) — rather than just sit near the
  level or add a type. A new Pokédex entry is still allowed (with a hint to box it). Teams under four are unchanged (they need bodies).

### Added — the free-switch box names the trainer's NEXT Pokémon
The "<Trainer> is about to use <Pokémon>! Will you change POKéMON?" box (Battle Style SHIFT) shows the name in-game, but the model was only told "its next Pokémon (N left)", so it could not choose a
matchup-based switch-in.
- The game has already picked the Pokémon when the box is up: `gBattleTextBuff2` (`0x02022AC8`) holds `[0xFD, 7, battler, gEnemyParty index, 0xFF]`. `MemoryReader.read_next_foe()` decodes that slot
  (None when the buffer is not that message, the slot is empty or fainted).
- `shift_switch_offer` adds `NEXT FOE: the trainer has already chosen <Pokémon> (L<n>, <types>; knows <moves>)`, the party-vs-foe roster (each teammate's best move and how hard it is hit) and, when the
  Pokémon on the field is badly placed, the better switch-in.
- Live regression on the Surge fight (real ROM): the offer names exactly the Pokémon `read_next_foe` reads.

### Fixed — the foe's ability counts (Levitate), and the League's shopping buys Revives and Hyper Potions
A watched League run (27 losses) kept using Earthquake / Magnitude on Gengar and Haunter (the observation said `×2 SUPER STAB`; their Levitate makes Ground moves do nothing), and restocked at the
Plateau's clerk — Max Potions ¥2500, Full Restores ¥3000, Revives last — when Hyper Potions (¥1200, 200 HP) and Revives (¥1500) are far better value.
- `annotate_moves` / `battle_summary` take the foe's live ability (`gBattleMons[1]`, already read for the party roster): a damaging move its ability blocks reads `×0 IMMUNE — NO EFFECT: this
  foe's Levitate ability` (Levitate vs Ground, Volt Absorb vs Electric, Water Absorb vs Water, Flash Fire vs Fire), is never the "Best move", and an all-blocked set raises the all-immune
  warning. `ABILITY_IMMUNITY` moved to `knowledge.move_semantics` (`ability_blocks`). The system prompt's legend says abilities count.
- `compute_stock_plan` from 7 badges: Revives are funded before the heals (par 5, stock-up 8, 45% of the money); at a mart with no Hyper Potion it buys Max Potions (par 3) before Full Restores
  (par 1), says "Hyper Potion" is the better grade elsewhere, and Full Heals' late par is 3. With Hyper Potions on the shelf (Saffron, Cinnabar) it buys up to 12.
- `shop()` with 7+ badges and ≥ ¥3600 goes to a mart that sells Hyper Potions first (Saffron when Fly can reach it — `go_to` flies; otherwise the nearest within ~150 tiles) instead of the
  Plateau's clerk; `shop(item=…)` still buys from the nearest mart. The "Bag is already stocked" early-out is the early game's only: late, the stock plan decides.
  The readiness text no longer claims Fuchsia / Celadon sell Hyper Potions (only Saffron and Cinnabar do).

### Added — the model is told about STAB, type immunities and the Revive rule
- `Your moves` marks a damaging move of the attacker's own type `STAB` (×1.5; not fixed-damage moves), the "Best move" line says `+ STAB`, an immune target reads `×0 IMMUNE — NO EFFECT`
  (and drops STAB), and a status move the foe's type blocks says so (`knowledge.move_semantics.STATUS_IMMUNE`: Thunder Wave vs Ground, Toxic / Poison Powder / Poison Gas vs Poison and Steel,
  Will-O-Wisp vs Fire, Leech Seed vs Grass). The system prompt explains the tags.
- Fainted Pokémon: the prompt says a Potion cannot help one (Revive, or `heal()` at a Center), and `use_item` refuses a Potion for a fainted target (and a Revive for a standing one) before
  driving the Bag menus, naming the fix.

### Fixed — travel flies when it saves walking; Victory Road no longer wedges; grind sites price Fly in
A watched run (Fly on the team, Thunder Badge) walked from the Plateau to Route 15 through Victory Road, Viridian Forest and Mt. Moon, to Saffron the same way and back through Diglett's Cave
— a wild battle every few tiles, each a model decision — and never called `fly_to`. It then ended wedged on Victory Road 1F ("No route through Victory Road 1F", 200 calls) after twelve
"trip to Victory Road 2F ended: blocked".
- `go_to` (and everything that travels through it: `heal`, `shop`, grind relocation, the quests) now flies first when that beats walking by 30+ tiles (`knowledge/flight.py`: a flight costs
  ~40 tiles; pure + tested). From open air it flies to the visited town nearest the destination; from inside a building it walks out when the door is near (≤ 60 tiles), then flies; with no
  walking route at all (Cerulean back west of Route 4) any flight wins. The result gets a "(Flew to X on the way — saves about N tiles…)" note. A failed flight (the Fly user fainted, a menu
  would not open) walks as before and is not retried from that map. `AgentClient._fly_ahead`.
- Victory Road: the boulder memory (`_vr_known`) was reset only when the FLOOR changed, so a heal trip out to Route 23 and back to 1F kept the old picture — a boulder dropped as "not
  reported" never came back and the planner found no route. `reader.map_epoch` (counts map changes) now resets it on every re-entry. And when the planner still finds no route with the boulders
  off their start tiles, `vr_route.reset_action` walks out of the floor (the entrance arrow on 1F) and back in: the cave reloads its boulders every time.
- Grind sites: `best_grass` no longer offers Victory Road 2F / 3F to someone not already standing there (go_to cannot solve the puzzles), and with Fly the walk to a site and the heal trips are
  priced at the cheaper of walking and flying to the town nearest it (`fly_towns`).
- Live tests: `go_to` flies from the street and from inside a Pokémon Center; the wedged 1F floor is reset (`vr1f_wedged` fixture).

### Fixed — late-game heal stocking (the League was reached with no real heals)
- A watched run stood at the Elite Four with 0 Potions and ¥0: the readiness check counted 10 Potions (20 HP) the same as 10 Hyper Potions, the stock plan kept buying Great Balls and
  one ¥2,500 Max Potion per visit at the Plateau, and nothing said the Plateau's clerk is the worst place to buy heals. Now:
  - `beat_readiness.effective_heals`: from a best Pokémon of L40 on (Victory Road, Elite Four) a heal counts for what it restores (HP ÷ 2.5 × level, at most 1): Hyper / Max Potion / Full Restore
    are 1, a Super Potion or Potion a fraction. The shortfall message names the grade and says Hyper Potions (¥1,200, +200 HP) come from the Saffron / Fuchsia / Cinnabar / Celadon marts.
  - `shopping.compute_stock_plan` with 7+ badges: Hyper Potions preferred whenever sold (the best HP per yen), par 12 (stock-up 14), heals get 60% of the budget and balls 15%, and Potions in the
    bag no longer count as stock toward Hyper Potions.
  - `money.supply_purchases` (the League prep at the Plateau) buys Revives then **Max Potions** (¥2,500, cheaper than Full Restores at ¥3,000; Full Heals cure status for ¥600), counting the heals
    already in the Bag by strength. The `elite_four` MONEY line explains where the money buys the most.

### Fixed — a loss keeps the Exp it earned (no reload after a blackout)
- `main._handle_blackout` used to load the most recent save of the session after every all-fainted blackout (the League's pre-door slot 3, a pre-gym slot…). That rewound every level and
  Exp the losing fight had given, so the model re-fought at the same levels (a watched run: 2 of 3 blackouts were undone). It now only advances the game's own whiteout (healed at a Center,
  half the money gone, Exp kept) and the model decides whether to train before retrying.
- The model was also *told* to `load_state` after a loss (system prompt, `load_state` description, the Elite Four beat tip, CLAUDE.md). All now say the opposite: `load_state` is for retrying a catch (slot 9).
  `NativeMGBAClient.latest_session_slot` (only the reload used it) is removed.

### Added — the full story chain clears without a model (#260)
- `python tools/scripted_run.py --goal clear --chain` drives the whole story with `ChainPolicy` (`agent/scripted_policy.py`): at each free moment it runs the next open beat's `quest(...)`, prepares when a quest
  says the team is not ready (grind, heal, shop) and hands every fight to the scripted battle rules. A **stall detector** names the first beat that cannot progress (the same failure three times, or 40
  calls on one beat with no new badge / key item / level / *new map*) and prints `STALL: <beat>: <why>`. From the Blaine fixture it now reaches the **Hall of Fame** (1,962 steps, brute force: 17 blackouts).
- What the first full-chain runs found and fixed: the **Pokémon Mansion** (statue press under a stale menu flag, a Mansion-aware walker, `_mansion_leave`), the **Nurse Joy tile** read from the live objects
  (One Island's Center differs), **Bill's One Island offer** at Cinnabar (answer NO: B), the **forced replacement** (IN_MENU *or* TRANSITIONING: `switch_pokemon`), the **optional battle party screen**
  (the SHIFT prompt: `advance_dialog` pressed A on it 4,700 times — it presses B), **`heal()` where no Center is reachable** (Victory Road: a go_to there wandered the cave pushing boulders; the Bag's
  Revives / Potions heal instead — `_field_heal`), and the policy's order of business (levels before Potions; train the weakest on Routes 22 / 23 *before* the cave, since the Plateau has no grass).
- The Indigo Plateau no longer strands the chain: the policy takes the optional `fly` beat (HM02) and teaches Fly to the lowest-level Pokémon that can learn it, so `grind()` can fly out of the Plateau; `shop()` treats a Pokémon Center with its own clerk (the Plateau's) as a Mart, so it buys there instead of walking to Viridian.
- `flee_battle` backs out of the FIGHT move menu with B and honours the later-turn action-menu value — a zero-PP move picked ("There's no PP left for this move!") made it re-pick the move forever (a 2,466-call loop in a chain run).
- Run logs: two runs started in the same second (parallel chain runs) no longer share one `logs/…/<timestamp>` directory and interleave their records; the second gets `<timestamp>-2`, and so on.
- `quest('elite_four')` flies to the Indigo Plateau (once it has been visited and a Pokémon knows Fly) instead of walking back through Victory Road, whose boulder puzzles reset when you leave the floor and which that driver cannot solve — chain run 16 spent 300 calls bouncing between Route 23 and the cave after a blackout. The stall detector ended that run on its own (reason `stalled`, 263 s).
- Routing from open water: a player surfing mid-lake on Route 23 (no region of its own) was routed from the map's plain node, whose South connection is a phantom (the bottom row is solid wall), so every `go_to` / `heal` / `quest` said "No walkable opening on the South edge" — 5,400 calls in chain run 15. A plain start on a regioned map now searches from the regions the water touches (the Surf-edge shores): to Route 22 by the south gatehouse's warp, to the Plateau through Victory Road's door.
- The chain no longer outlives its own stall: `run_episode(should_stop=)` ends the run with reason `stalled` when the policy records one (`tools/scripted_run.py` wires it; `--no-stop-on-stall` keeps the old behaviour). The detector had flagged run 15's loop at about call 100 and nothing acted on it; replayed against the run that cleared the game, neither stall rule fires.
- `heal()` falls back to the next-nearest Pokémon Center when the nearest one can't be reached: from Route 23 the graph's nearest is the Indigo Plateau's (via a North edge that isn't walkable), so it now goes round to Viridian's across the Surf gap (`nearest_of_kind(..., exclude=)`, and a `go_to('map:<bank>,<id>')` destination for Centers, which have no names). A chain run with the whole party fainted there had looped 700 calls.

### Changed — the audit's priority-3 items (2026-11-23)
- **Boss lead by matchup.** `boss_lead_vs(party, trainer)` picks the healthy attacker whose moves hit the trainer's team hardest and who takes least from their types (level a small tiebreak) instead of simply the highest level: against Lorelei's Water / Ice team a L54 Charizard is a bad lead and a L45 Pikachu hits most of it for double. Used by `challenge_leader` (the gym's leader) and in each Elite Four / Champion room.
- **Stall detector absolute cap.** The chain's stall rule counted a level gain as progress, so a grind that crawls never tripped it; a beat is now also a stall after `MAX_BEAT_CALLS` (1500) calls in all.
- **LLM connection trouble is waited out** (`agent/llm_retry.py`, `LLM_RETRIES`, default 8): connection resets, timeouts, rate limits and 5xx get a 2→60 s exponential backoff inside the call instead of costing the run one of its 30 one-second retries each (a dozen `APIConnectionError`s in errors.log; ~30 s of bad network ended an hours-long run). Anything else (a 400, a bad key) still fails at once.
- **Bill's invitation.** `answer_prompt('yes')` to "Come with me to One Island?" is answered NO while the scene is pending (YES starts the Sevii detour — a ferry the router cannot plan, so a run that said yes had no way home); the dialogue was already advanced with B for the same reason.
- **A flaky test:** `test_uncapped_emulation_presents_at_most_present_hz` counted renders in 0.2 s of wall time and failed under load; it runs on a fake clock now.
- **Not done, on purpose:** a Seafoam crossing driver (Fuchsia → Cinnabar already goes round automatically in ~17 s, or Fly) and tag-switching in autopilot trainer fights (a switch costs a turn against a trainer; `grind()`, the Exp. Share and travel-lead already close the level gap, and the LLM plays its own fights).

### Added — PP items, Elite Four scouting, forgiving tool arguments (the harness audit's P2 items, 2026-11-23)
- **Ether / Max Ether / Elixir / Max Elixir work, in the field and in battle.** `use_item('Ether', move='Ice Beam')` refills that move (default: the most depleted); an Ether asks "Restore which move?" with a list over the party menu, so the driver reads that list's cursor (`Addr.PP_MOVE_CURSOR`, found by diffing EWRAM) to the wanted row; an Elixir refills every move of the chosen Pokémon (auto-picked: whoever is shortest of PP). In battle it costs the turn and a full-PP Pokémon is refused without one. `_field_pp` spends them where PP ran out (an Elixir on a team member 15+ PP short, an Ether on a damaging move at 0 PP) — in the sealed rooms' heal and before each Elite Four leader. They are only found, never sold, so the run that held an Ether and an Elixir all game now has a way to use them.
- **Elite Four scouting.** At the Plateau's Center the observation lists all five trainers' teams, types and watch-moves ("ELITE FOUR AHEAD…"); in each room "THIS ROOM: …" gives that trainer's brief. `team_report` (after eight badges) now says how the team answers each trainer: how many of their Pokémon it hits super effectively, how many members are safe from their types, who has no answer.
- **Tool arguments the model gets slightly wrong are repaired, not refused** (`agent/tool_args.py`): `use_hm {"hm": "Dig"}` → `move`, `go_to {"location": …}` → `destination`, a single stray name for the one missing argument, "5" → 5; a truly missing argument is answered with the tool's own signature ("use_hm needs move — use_hm(move: …). You sent: hm='Dig'") instead of a bare `Tool use_hm failed: 'move'`.

### Fixed — the harness stalls found by mining 16 watched runs (2026-11-23)
- **Stall snapshots.** On the 5th identical failing tool result in a row the client saves an emulator state under `logs/runs/<ts>/stalls/` (`stall` in that tool's run-log record; at most 8 per run): a stall can now be loaded as a live-test fixture — the Route 23 loop below could not be reproduced from logs alone. `No walkable path…` joins the failure heuristics.
- **Dead connection edges.** From Route 23's lake shores go_to planned a phantom `North` connection (that half is only reachable through the cave); go_to_map answered "Couldn't get to the North edge … no walkable path to any of its tiles", the player had moved a little on the way, and that counted as progress — 10-30 calls per trip (37 in the last two runs). That answer now marks the edge dead at once, the router plans around it, learned-dead edges are forgotten at most once per call, and when nothing is left go_to says "Every way to X is blocked right now (dead: …)".
- **The heal gate catch-22.** On Victory Road 2F / 3F go_to refused ("heal() at a Pokémon Center") 24 times while heal() could only use the Bag; the hurt party is a warning there now.
- **`quest('victory_road')` "already done"** from inside the cave or south of it (the boulders reset when you leave): only the Plateau side answers that now.
- **Wrong diagnosis in caves.** walk_to said "Couldn't start Surf — no reachable shore" (27×) for cave targets cut off by boulders: Surf is only tried when the Surf grid differs by real water; a cut-off Victory Road target now says it is a puzzle barrier and points at quest('victory_road') / go_to.

### Added — an optional rule: the League's recommended levels rise with every loss (requested 2026-11-23)
- The Elite Four's BASE level shortfall is always a wall (best Pokémon L54, five at L46+). On top of it an OPTIONAL rule makes the bar climb with every loss: `LEAGUE_LOSS_BUMP` levels (default 2) per loss on the best-Pokémon and depth levels (capped at L70 / L62). `LEAGUE_LOSS_RULE` picks how hard it pushes — `advise` (default): after a loss `quest('elite_four')` says once per loss count that the bar went up, what is short, and that training is *encouraged, not required*, and the next call goes ahead (the model keeps its autonomy); `wall`: the raised levels are refused on every call; `off`: no escalation. The loss count lives in the journal (`league_losses` in progress.json), counted when a call that was in an Elite Four room next finds the player outside it (the only way out of a sealed room is the whiteout).

### Fixed — Full Heals are used, and the Elite Four is a level wall (watched runs of 2026-11-22)
- A run bought Full Heals and used none in 1,700 calls: its Lapras fought a whole Elite Four room paralysed. Nothing in the observation tied a status to the Bag. The battle observation now says so — "STATUS: Lapras is paralyzed — it moves at a quarter speed… Worth a turn: use_item('Paralyze Heal') (you hold 2), or switch" — naming the cheapest cure the Bag holds (specific cure, then Full Heal; a Full Restore only once the mon is also low) and how urgent it is (asleep / frozen: now). The sealed-room `heal()` and the League quest's top-up before each leader now cure statuses from the Bag too (`_field_cure`, never a Full Restore) and `heal()` no longer answers "already at full HP" for a team that is only poisoned / paralysed.
- A run threw itself at the Elite Four eleven times with a team under the recommended levels: the readiness check warned once and every later call went ahead. For `elite_four` the LEVEL shortfall (best L54, five at L46+) is now a wall — "Not ready … and this one cannot be skipped" on every call, pointing at grind() (Victory Road is the nearest ground); supply shortfalls keep their one-time warning.

### Fixed — the Elite Four's rooms are sealed, and the agent now knows it (watched run of 2026-11-22)
- After beating Lorelei a run called `heal()`, `shop()`, `go_to('Pokemon Center')` and `walk_to` from the sealed room for ~300 calls ("No walkable path ... (6,12)"): the room's door closes behind you and there is no Center, shop or way out until the Champion falls. `knowledge/league_rooms.py` names the five rooms; inside one: `heal()` heals from the Bag only (Revives for the fainted, then the smallest Potion / Full Restore for anyone under 60%) and says what is left; `go_to` anywhere else answers with the seal instead of wandering; the observation carries an "ELITE FOUR: SEALED IN…" line (Full Restores / Revives / Potions left, party standing, and that a whiteout returns you to the Plateau's Center with the League reset); and `quest('elite_four')` tops the team up from the Bag before each leader.
- `_field_heal` counted a refused item ("In a battle — use the battle version.") as used — twelve phantom Revives in one reply; only a result that starts "Used" counts now.

### Changed — grind in Victory Road, not at the other end of the map (watched runs of 2026-11-22)
- After the cave, `grind()` sent a L45-52 team to Cinnabar's Mansion (309 tiles + a Surf from Route 23) while Victory Road's wild L32-48 were next door: the cave was not a grind site at all. The three floors are now `CAVE_GRIND_MAPS` (every floor tile encounters, like the Mansion; pacing never steps on warp tiles, so the entrance arrow warp is safe). `best_grass` offers 1F from anywhere (it is open from the entrance) and 2F / 3F only to someone already inside the cave, where they sit behind the boulder puzzles. From Route 23, the Plateau and Viridian, 1F now beats the Mansion at both L45 and L52.
- Heal trips were mis-measured: the nearest Center to the cave counted the Plateau's (behind the puzzles), so the cave looked 63-104 tiles from help when the walk that is open is Viridian's (126+). `pokecenter_tiles` ignores the Plateau's Center, and from the south side go_to("Pokemon Center") / heal's next-Center search skip it too (the Plateau side keeps it). A heal in the middle of a grind session in the cave walks OUT by the reverse puzzle to Viridian's Center instead of draining the Bag item by item; outside a grind session heal() in the cave is unchanged.
- `got_fly` is a valid milestone (record_milestone); the journal of this run now records that Pidgeot knows Fly (taught by hand).

### Changed — Fly is a gate for Victory Road (watched run of 2026-11-22)
- Past Victory Road there is no grass and no quick way home, so entering the cave now needs Fly: `quest('victory_road')` answers "Not yet — Fly first" (before the readiness warning, no "go anyway"), and `go_to` into Victory Road 1F reports the same gate before walking anywhere (`knowledge.gates.MAP_GATES[(1,39)]`). A Pokémon that knows Fly plus the Thunder Badge meets it; so does a visit to the Plateau already made (the run that is stuck on the far side is not locked in), and a party nobody in which could ever learn Fly (an impossible gate would stall the trip for good).

### Added — the way back south through Victory Road, and a Fly warning (watched run of 2026-11-22)
- A run that cleared the cave and reached the Plateau without Fly could not leave: the Plateau side of Route 23 has no reachable grass, so `grind()` needed Route 22 and beyond, and go_to walked into the walled-in ladder pocket at 2F (36,17) ("No walkable path ... (48,12)"). Leaving the cave north RESETS its switches, so the way down is the puzzle in reverse. `vr_route.plan_back` searches floor hops (3F: 4 pushes → 2F west: 1 push → 1F: 2 pushes → the south exit) and `go_to` runs it (`_vr_back`) whenever it starts inside the cave heading anywhere but the Plateau — checked at every hop, so the generic route can no longer wander into the pocket; standing on a ladder the planner steps off and back on.
- The first `quest('victory_road')` of a session warns when nobody can Fly: past the cave there is no grass and no quick way home (the Elite Four wants a L54 best Pokémon and five at L46+). Calling it again goes ahead.

### Fixed — go_to from inside Victory Road runs the boulder quest (watched runs of 2026-11-22)
- Two runs stood on Victory Road 2F calling `go_to('Indigo Plateau')` and `walk_to(36,17)` for hundreds of calls ("No walkable path ... target may be blocked"): the south-east ladder sits behind a barrier that opens only when the boulder dropped from 3F is pushed onto 2F's second floor switch, which the warp graph cannot plan. `go_to` to the Indigo Plateau from any Victory Road floor now hands over to `quest('victory_road')` (verified from the stuck run's own checkpoint, which then reaches the Plateau), and the stall advice inside the cave points at the quest instead of "keep pushing, call go_to again".

### Fixed — Victory Road's boulder push from the entrance tile no longer walks out of the cave (watched run of 2026-11-22)
- 1F's switch boulder ends up at (11,19), directly above the entrance's down-arrow warp (11,20), so the last push UP is made FROM that tile. `_vr_push` answered the 'Use Strength?' box with `_answer_field_yes`, whose choice-box probe taps Down — which fires the arrow warp: the player left the cave, the boulders reset, and the 19-push sequence started over. On an arrow tile the push now confirms with A only (`_confirm_with_a`).

### Fixed — a trip inside the Mansion no longer doubles back to 1F after a fight (watched run of 2026-11-22)
- Getting to Mansion B1F means 2F → 3F → a hole down to 1F's walled middle → the stairs. go_to re-routes from the current map after every battle, and its warp graph (fewest hops) said "back down to 1F" from 2F; the Mansion planner then led up again, so each wild encounter on 2F cost a lap. Between two Mansion floors go_to now follows the Mansion planner (`_mansion_to_floor`: stairs, holes and the statue switch with the barriers as they are now), re-planned after every interruption.

### Fixed — grinding in the Mansion no longer paces onto the staircase (watched run of 2026-11-22)
- `grind()` in the Pokémon Mansion changed floors over and over: you arrive standing on a staircase, and the first pacing step warped to the next floor, which arrived on another staircase. `_wander_step` now never steps onto a real warp tile (or presses a staircase's own direction), and the Mansion's grind tiles exclude warp tiles. The live Mansion test now asserts the floor stays put.

### Added — shinies are caught, Mom heals, the Mansion is grind ground (watched run of 2026-11-21)
- **Shiny Pokémon are recognised and caught, never knocked out** (a watched run ice-beamed a shiny Tangela). `PokemonStatus` now carries the OT id and `is_shiny` (the Gen III rule: TID ^ SID ^ PID-high ^ PID-low < 8; a
  wild Pokémon is generated with the player's ids). A shiny wild foe is a **one-shot** (`knowledge.one_shot`, the Snorlax protocol): the observation says "✨ SHINY …: catch it whatever the species — even one you own or
  'not worth a ball'", saves the battle-start state in slot 9 (`load_state(9)` retries if it faints), tells the model to chip it with the gentlest move / put it to sleep, then `catch()`. The autopilot never touches it
  (`_auto_fight`, `grind`'s auto-battles, `go_to`'s flee/auto-fight — all hand it to the model), `flee_battle` refuses while there are balls, the event stream prints a ✨ `shiny` event (and `shinies` in the run stats),
  and the scripted policy chips and catches it too.
- **`heal()` can heal at home**: once Rival Gary is beaten, Mom's house in Pallet Town counts as a Pokémon Center (`MAP_KIND[(4, 0)] = "home"`, `HEAL_KINDS`) — free, and a few steps from Route 21 where the grinder used to
  walk to Cinnabar's Center every time. `go_to('Pokemon Center')`, `heal()`'s fallback and the grind planner's heal-trip cost all use whichever is nearer; `_heal_at_home` walks next to Mom and talks until the party is whole.
- **`grind()` works inside the Pokémon Mansion** (no tall grass — every floor tile rolls an encounter, Grimer / Koffing / Ponyta / Muk L26-38): the four floors are grind sites (`CAVE_GRIND_MAPS`), and the grass step
  paces on tiles whose metatile encounter type is "land" (`TilemapReader.land_encounter_tiles`).

### Changed — the ace no longer leads every fight outside a gym
- **Why the ace kept a ~8-level lead** (read from the last 13 logged runs): it started 7 levels ahead and, after every `grind()`, `_restore_ace_lead` put the highest-level Pokémon back in slot 1 — so
  every quest / gym-trainer / autopilot / travel fight outside `grind` was the ace's (it led 73-95% of overworld ticks in the recent runs, 2-30% in older ones). It got ~24% of the XP against ~15% for
  each other member, and equal shares can never close a gap.
- `knowledge.party.travel_lead`: the **lowest-level healthy attacker within 12 levels of the top** leads (a kill pays the same XP whoever lands it); the strongest only when nobody else is close or healthy.
  `grind()` ends by setting it. `boss_lead` (the strongest healthy attacker) is set by `challenge_leader` and in each Elite Four / Champion room (`_set_boss_lead`), so bosses are still the ace's.
- `better_matchup` breaks a full tie by the LOWER level (it picked the highest). Real menus verified: Caterpie leads after a grind, Bulbasaur for a leader, Caterpie again.
- Not done: tag-switching in the autopilot's trainer fights (the way `grind` does for wild ones) — the next lever if the gap persists.

### Fixed — Fuchsia -> Cinnabar planned a crossing that does not exist
- **Route 20 is two seas, not one**: collision tiles (a wall at x=50-51, blocks at x=80-85 on rows 15-16 — decoded from the decomp's map.bin and confirmed by walking into them) seal its east half (Route 19's)
  from its west corridor (Cinnabar's); the way across is the Seafoam cave. The graph had a plain West connection, so `go_to` surfed to Route 20's east end, said "Reached the West edge but could not cross" (it
  was the EAST end) three times, and only then looped round through Lavender, Vermilion and Pallet. The graph now has separate east / west sea nodes (`knowledge/map_graph.py`, `route20_west`), so the trip goes round
  at once (live: 18 calls, ~17 s, Route 20 never entered).
- Not automated: the cave crossing itself (a live attempt found "no walkable path" inside B2F and ended wandering B3F); until a Seafoam driver exists the long way (or Fly to Pallet) is the route.
- `_go_to_map` no longer says "Reached the X edge" when it never got there. The gate loop now bans maps whose Snorlax is still asleep when the region-blind fallback proposes them, and searches again.

### Added — the Exp. Share follows the lowest-level Pokémon (adaptive)
- Once the Exp. Share is owned (Oak's Aide, Route 15's west gatehouse, 50 species caught — `quest('exp_share')`, announced in the observation's OAK'S AIDE line), `_maintain_exp_share` keeps it on the
  **lowest-level party member** and moves it as levels change: it takes the item back from the old holder (new `_take_item`: Start → POKéMON → the Pokémon → ITEM → TAKE) and gives it to the new lowest
  (`_give_item`). It runs once per overworld tick in `run_episode` and is a party-and-Bag read when nothing is needed; a tie keeps the current holder (no thrash), a move that fails twice for the same
  party is dropped until the party changes. Verified on the real ROM, including a Pokémon with Cut / Strength in its sub-menu.

### Added — the Running Shoes, the bike state, rod tiers, a map-aware one-shot (#269, #272: the rest)
- **Running**: once `FLAG_SYS_B_DASH` is set, `walk_to` / `go_to` and grass pacing hold B outdoors (`mgba.run_step`: B + direction for 4 frames, release 4 — 8 frames a tile instead of 16; 10 presses
  = 10 tiles, no overshoot). Vermilion -> Route 11 takes 360 frames instead of 704. Not indoors (the map header's `allow_running` is false there, and a press is half a step), not on a bike or Surf, not on
  the boulder / switch floors (Victory Road, Seafoam, Silph, the Mansion) or while arrow tiles slide you. `USE_RUNNING_SHOES=false` turns it off. `tools/gen_map_dims.py` now also emits `RUN_ALLOWED`.
- **The observation says how you are travelling**: "riding the Bicycle (…the Cycling Road keeps you on it, one way: south)" / "surfing".
- **Rod tiers in the wild data**: fishing rows are `old rod` / `good rod` / `super rod` (the decomp's ten fishing slots: 0-1, 2-4, 5-9) instead of `fish`, so `where_to_find` says "Gyarados — S.S. Anne
  (exterior) (super rod L15-25)" and the dex plan points at the quest that gets the rod (`quest('super_rod')`).
- **One-shot, map-aware**: the Power Plant's static Electrodes (the only Electrode source before Cerulean Cave's L58+) get the ONE-SHOT protocol and are never autopiloted; a failed Snorlax catch now says
  `load_state(9)` goes back to the start of the fight.

### Changed — grind sites are chosen by walking cost, Center distance and the next objective
- A watched run trained on Route 13, ~190 tiles from the nearest Pokémon Center, and walked back to Lavender to heal four times. `best_grass` scored a route by how well its wild levels fit plus **0.15 per
  map hop** — a hop is anything from a 10-tile doorway to Route 12's 120-tile pier, and the Center was never in the sum. Now (`knowledge/distance.py`, `knowledge/map_dims.py` generated by
  `tools/gen_map_dims.py`): cost = level misfit + the walk there (or, with an objective ahead, the *extra* walk it adds to reaching the next gym's city) + 1.5 round trips to the nearest Pokémon Center,
  all in tiles (80 tiles ≈ one level of misfit). From Fuchsia / Lavender / Route 13 at L24 it now picks Route 15 / Route 12 instead of Route 13 / 14.
- Not done: caves (Rock Tunnel, Mt. Moon, Seafoam) and fishing as training spots — grind only recognises tall grass tiles; the level data for caves exists.

### Changed — shop() buys the best this mart sells and uses spare money; the Celadon stones
- The restock plan was by badge count (Ultra Balls at 5 badges, par 10 whatever the money): a player with ¥26,000, 17 balls and one Potion bought the same ten of each. `compute_stock_plan` reads
  what the open buy menu lists: the best ball (Ultra > Great > Poké) and healing tier (Hyper > Super > Potion) that mart has and the money supports, within each family's share of the money, then —
  with ¥3,000+ spare — stocks up (25 balls, 15 potions, 10 Full Heals, 5 Revives, Full Restores at the Plateau). Cheaper balls in the bag count half toward a better tier. The reply says which better
  grade another mart sells. A ¥26,000 Fuchsia visit: 8 Ultra Balls, 8 Super Potions, 5 Full Heals, 2 Revives (¥21,200).
- Evolution stones: `shop(item='Thunderstone')` (Dept. Store 4F, ¥2,100) was already supported — now live-verified — and the Celadon observation lists the stones a party member would use
  (`stone_wants`: Pikachu / Growlithe / Vulpix / Gloom / Weepinbell / Poliwhirl / Shellder / Staryu / Exeggcute; Eevee and the unsold Moon / Sun stones are left out).

### Fixed — found by the live suite on this PR
- **A wandering NPC broke the gift quests**: the Route 16 house's woman has `MOVEMENT_TYPE_WANDER_AROUND`; after a few frames of difference in how we walked in she stood one tile off her home tile and the
  player pressed A at an empty one (`quest('fly')`: "Talked to the woman but nothing was given"). `_talk_to` now aims at the nearest loaded NPC when none stands on the home tile, and `_gift_errand`
  looks again up to three times.
- **Victory Road's boulder pushes overshot**: `_vr_push` held the direction 20 frames, longer than one 16-frame step, so depending on the frame phase it pushed the boulder twice and carried it past its stop
  ("No route through Victory Road 1F"). The hold is now 12 frames (exactly one tile).
- `_warp_exit_tile` now moves off a listed warp tile only to a real warp within one tile, and otherwise keeps the old door-centre rule.

### Fixed — the shuffle at stairs and exit mats
- **Directional staircases** (the Celadon Dept. Store's) fire on a LEFT / RIGHT press while you stand on them. `walk_to` nudged Down first, stepped off, replanned and stepped back on: about twenty
  D / U cycles per floor before a probe found the side. It now presses the tile's own direction first (`TilemapReader.warp_press`: arrow warps and directional stairs).
- **Exit mats**: a map's warp-event list can name tiles the game never warps from — the Dept. Store 1F lists (1,15) and (3,15) (walls) beside the real arrow mat (2,14). `go_to` aimed at the wall and
  pressed Down into it ~70 times. `_warp_exit_tile` now prefers tiles whose metatile behavior is a real warp (`is_real_warp`). Up to 4F and back out: 297 + 259 presses -> 150 + 41.

### Fixed — a lingering move-learn state made the driver press A into the battle menu
- A watched run (Venonat L25, Leech Life on offer) lost ~13 minutes of game time and four watchdogs: the Pokémon used Foresight (move 1) about 24 times, from 40 HP to fainting, while
  `use_move`, `grind` and `advance_dialog` all stalled. `learnMoveState` LINGERS at 1 after a decline, and the "is a delete box up?" check read exactly that (plus a move on offer), so the driver
  pressed A at the ordinary battle menu — FIGHT, then slot 0 — and re-resolved the same "prompt" until the watchdog fired. Reproduced live (7 resolves, PP 40 → 16, HP 27 → 0).
- The box is now live only while the battle script is WAITING on it: `gBattlescriptCurrInstr` sits on the "Delete a move?" command (`SCRIPT_LEARN_DELETE` 0x081D8A08) — and, for the give-up box,
  on 0x081D8A17 (both read from the real prompt). `_accept_forget_slot` presses A only while the pointer is there, waits for the summary before steering, and backs out with B / A only when the
  script is on the give-up box; the drive loop stops after three resolves of one prompt instead of 300 iterations. Real prompts (forget slot 0-3, decline, back-to-back) still work.
- The suite caught a regression in the first cut of this fix: while the "is trying to learn X" texts print, `learnMoveState` can already read 1 (stale) with the script still before the box, so nothing advanced
  the text and other code mashed A at the real box (Ivysaur forgot Tackle for Sweet Scent in the SS-ticket quest). Those texts are now advanced with the policy's own button — B to decline, A to learn.

### Added — the Cycling Road: Route 16's Snorlax and bike-aware routing (#272 / #269, the rest)
- **`quest('snorlax_16')`** (optional beat): the second Snorlax at Route 16 (31,13), Celadon's side. Same flute-and-fight script as Route 12's — the fight goes to the model under the one-shot protocol, never
  the autopilot — and `FLAG_HIDE_ROUTE_16_SNORLAX` (0x080, set when the fight starts) is the proof. Verified live from the stalled run's Route 16 state.
- **Celadon -> Fuchsia over the Cycling Road** when the Snorlax is gone and the Bicycle is owned: Route 16's gate house -> Routes 17-18 -> Fuchsia in one `go_to` leg (9 hops instead of the 20 through Lavender).
  `SNORLAX_LINKS` now holds Route 16's crossing too; the gates say "quest('snorlax_16')" / "quest('bike')" when one is missing.
- **On the Cycling Road the game keeps you on the bike**, and `walk_to` used to try to dismount there: "Interrupted while walking to the South edge (TRANSITIONING)" and the Start menu left open. It now
  rides (`FLAG_SYS_ON_CYCLING_ROAD`, 0x830). Live-verified with real bikers on the slope: the fights, a heal mid-road and the arrival.
- **The road is one-way**: Route 17's pull-down tiles carry you south and the bike cannot climb them, so Fuchsia -> Celadon is never planned over it (it went "stuck at Route 17 (North edge)" first).
- Gate hunting fixes: a crossing inside the map you stand on (a Cut tree, a Snorlax) no longer bans the whole map, and the region-blind fallback may not be taken as the alternative when it would walk
  through Route 12 / 16 (it cannot see the Snorlax there).

### Fixed — go_to('Fuchsia City') said "you need Surf" when the land route was open
- Two watched runs reached four badges and then stalled on Fuchsia (about 20 identical `go_to('Gym')` / `quest('koga')` / `quest('surf')` calls, each "Route 21 is open water — you need Surf"). The
  generated region grids see a sleeping Snorlax's square as a wall, so Route 12's pier was split in two with only a water link between the halves; the planner chose a 24-step sea trip via Pallet, and
  the land alternative carried a Surf step too. New `SNORLAX_LINKS` (`knowledge/map_graph.py`) model the crossing as a `snorlax` step, held by `knowledge/gates.py` to the wake flag (0x253): asleep, the
  answer is "wake it: quest('snorlax')"; awake, `go_to` walks Lavender → Route 12's gatehouse → over the Snorlax → Routes 13-15 (live-verified from Route 16, 3 calls).
- Route 17 (the Cycling Road) is gated on the Bicycle: Route 16's south edge used to pass the flute gate and then fail with "Reached the South edge but could not cross".
- The team report no longer lists a Surf gap as a reason Fuchsia is out of reach (the HM comes from inside it).
- Checked end to end: `quest('bike')` from Route 16 on foot reaches the Fan Club (voucher) and the Cerulean Bike Shop (Bicycle, key item 360), and `go_to('Fuchsia City')` still takes the Route 12 road afterwards (new live test).

### Fixed — the Pokémon Tower's ghost Marowak is not catchable
- A watched run threw 18 Poké Balls at the Marowak on 6F ("It broke free!" every time) until the watchdog fired: the game dodges every ball in a ghost battle (`BATTLE_TYPE_GHOST`, bit 15 of
  `gBattleTypeFlags`), and our encounter hand-off had said "Worth a ball: a NEW Pokédex entry". `catch()` now refuses without throwing, the `quest` / `grind` encounter hand-offs and the battle observation
  say it can't be caught and to defeat it with `use_move`.

### Fixed — from a one-hour watched run (150 steps, 798 model calls, three watchdog stalls, eight `quest('flash')` calls)
- **A Disable that lands mid-turn stalled `use_move` (and `grind`'s trainer fights) for 2.5-4 min of game time.** The foe's Disable can land after `use_move`'s pre-flight read; the move menu then
  bounced the commit through 60 text-advance rounds until the watchdog fired, and `grind`'s auto-fight (which goes through `use_move`) did the same against a Grimer. `use_move` now re-reads the Disable
  state each time the move menu is up and answers "X is DISABLED" at once, and stops after three commits that never spent PP (Taunt, a sleeping or paralysed Pokémon…).
- **`quest('flash')` before Cut said nothing useful.** The Route 2 east building is behind a Cut tree; the model called it eight times, each time learning one more hop of flash → cut → ss_ticket. It now answers
  up front with the chain (misty → ss_ticket → cut → surge → flash) and the beat to run first (`story_beats.first_open`).

### Changed — the system prompt keeps what changes as you play last
- `Progress` (badges, towns, `Battles: N won`), the loss lessons and the `Navigation` block moved from the top of the system prompt to a final "Current status" section, so the ~5.7k-token static rules are an
  identical prefix every step. The run's prompt cache hit rate was 54% overall and only ~224 tokens on the first call of most steps (the first changed line sat ~224 tokens in). The tool list still changes with
  the screen (battle vs overworld) and the history window still slides, so the rest of the prompt cannot be reused across steps; compare `cached_tokens` in the next run.

### Added — new-game choices in `.env`
- `STARTER` (bulbasaur | charmander | squirtle), `PLAYER_NAME` and `RIVAL_NAME` (up to 7 letters) in `.env` set what `quest('new_game')` picks; blank keeps bulbasaur / RED / BLUE. Options typed in the call
  (`quest('new_game charmander name=ASH')`) still override them, and the new-game hint tells the model what `.env` chose. `girl` stays a call option. The live new-game test now drives the real ROM from these variables.

### Fixed — the PC, from a watched run whose PC never worked (ten `pc` calls, none succeeded)
- **A bug in two error messages:** `pc swap` / `pc withdraw` with no match printed `<bound method PCMixin._pc_boxes …>` instead of the box list (`{self._pc_boxes}` for `{self._pc_boxes()}`).
- **`box:4` copied literally.** The model sent the placeholder from the docs; a reference is `box:slot` as numbers — `'1:4'` (box 1, slot 4). `box:4`, `box 1:4` and `box1 slot 4` are now understood or answered with a hint,
  and the tool description gives the example.
- **The skill recovers.** A failed PC open used to leave the 'Which PC?' menu showing (the next call: "open the PC from the overworld"). It now backs out through the menus, tries once more from scratch, reports what the
  screen showed (callback, context, menu cursor, position) and, after two failed calls in a row, tells the model to stop retrying. A menu left open before the call is cleared first.
- **Failure screenshots.** When a tool's result reads like a failure ("Couldn't…", "didn't open…", "was stopped: no progress", "stuck at…"), the current frame is saved to `<run dir>/shots/<seconds>_<tool>.png` and
  the path is recorded in that tool's run-log event (`shot`). At most 40 per run, spaced 5 s apart, one per repeated failure (`agent/failure_shots.py`).
- Not found: why the PC would not open in that run — it did not reproduce on a clean Cerulean Center fixture (deposits of party slots 3-6 all worked). The next failure will leave a picture.

### Fixed — four problems from a watched new-game run
- **`heal()` hung in a trainer battle.** Its trip to the Center auto-fought a trainer with a hurt party (`mode="flee"`): two Pokémon fainted and the watchdog stopped it ("no progress for 3.4 min of game time"), twice. With a
  must-heal need, a trainer on a heal trip now goes to the model like any encounter — "switch to a healthy Pokémon or use a Potion" — and `heal()` resumes the trip. Healthy parties still auto-fight.
- **Stale moves and empty PP.** `use_move` with a move the Pokémon no longer has (Bulbasaur replaced Tackle) or one at 0 PP now lists the moves it really has WITH their PP ("usable now: Sleep Powder (PP 15)…", or "Struggle is
  all that's left" when everything is empty). The model had called `Tackle` / `Vine Whip` again and again.
- **Over-long nicknames.** `catch(nickname=…)` with more than 10 characters is shortened (whole words while ≥ 5 characters survive: "Beaky Blinders" → "Beaky") and the reply says so, instead of throwing no ball and
  asking again — that cost a call three times.
- **`switch_pokemon` right after a battle.** The post-battle fade reads as "not a battle"; the tool answered the same one-liner five times. It now settles to the field first and says where you are and what to use instead
  (`reorder_party`, `heal()`, `go_to`).
- Verified: unit tests for all four; a live test for the last three on the real ROM. The heal hand-off is covered by unit tests only (the original fight is not reproducible from a fixture).

### Fixed — a new game starts with a blank journal
- `START_NEW_GAME=true` used to keep `logs/progress.json`: its `delivered_oaks_parcel` milestone made `quest('new_game')` answer "already done" at the title screen. A new game now backs the journal up
  (`progress.json.pre-newgame-<time>.bak`) and starts from the defaults (`LongTermMemory.start_fresh`).

### Fixed — the opening of the game: what a watched new-game run got wrong
A run from the title screen took the parcel from the Viridian Mart clerk and then never delivered it. The log showed why:
- **No cue to deliver it.** The `STORY NEXT` line was only shown after the first badge. It now shows before the Pokédex too, with an `OAK'S PARCEL is in your bag — take it to Prof. Oak: quest('parcel')` line (and an
  `OPENING:` line while the parcel is still to fetch).
- **Nudges that sent it the wrong way.** READINESS said "shop(), catch more, Brock's gym is next — grind(13) first", the Mart said "call shop()" and `go_to` appended "Before the next leg: shop()". Until Oak has the Pokédex the
  Viridian Mart sells nothing (the model called `shop()` a dozen times), Oak gives the first Poké Balls and the road north is shut — so `readiness.assess(pokedex=False)` advises only a heal, the Mart hint is hidden and
  `shop()` there answers why ("the clerk only hands over Oak's parcel").
- **The rival's first battle.** It opens with ~35 text boxes, including Oak's battle tutorial, whose menus the move-menu check never recognises: `use_move` answered "the battle menu did not respond" three times.
  The new-game driver now plays that intro and tutorial through (and `use_move` / `advance_dialog` wait longer: 60 / 150 steps instead of 20 / 60) and tells the model when it is its turn.

### Added — the live suite runs as a gate, and its first full run found a regression (#279)
- `tools/live_suite.py`: one command for the real-ROM suite — preflight (ROM, `work.sav`, every fixture a test loads, the binding), summary, `--changed BASE` (only when the diff touches guarded code), `--post-status` (publishes
  the `live-suite` commit status for HEAD; full runs only). `.github/workflows/live-gate.yml` keeps that status `success` ("not needed") or `pending` ("run the live suite") on every pull request. `docs/live-ci.md` weighs the options
  (self-hosted runner, local attestation, building the ROM from the public decomp in CI — whose SHA-1 matches the retail ROM) and what is left for the owner to decide (making `live-suite` a required check; the decomp-build route).
- **Fixed what the first full run found:** a Victory Road regression from the Articuno PR (Surf started from the wrong shores first; the old nearest-first search is back, elevation-3 shores are a second pass), a stale tea-test assertion,
  test-order leaks (the live harness now resets skill state and long-term memory on every fixture load) and two luck-dependent tests. 78/78 in about 31 minutes.

### Added — `quest('new_game')`: the model can start the game from the title screen (#260)
- `START_NEW_GAME=true` boots the ROM to the title with no save loaded; `quest('new_game')` (alias of the `parcel` beat, which had no driver) then plays everything up to the Pokédex: the controls pages and Oak's speech, BOY/GIRL, the
  player's and the rival's names on the keyboard, the bedroom, Oak's "Hey! Wait!" intercept at Route 1, the lab, the starter, the rival's battle (handed to the model like any trainer fight), Viridian's Mart (the clerk's forced scene
  hands over Oak's Parcel) and Oak (the Pokédex and five Poké Balls: `FLAG_SYS_POKEDEX_GET`, what the chain's `parcel` beat checks). Every phase is resumable; screens are told apart by the main callback, the live cursor menu and
  the party / flag / key-item state, never by counting presses. Options follow the name: `quest('new_game squirtle name=KYLE rival=GARY girl')` (default: Bulbasaur, RED, BLUE, boy).
- With a save present the title shows CONTINUE above NEW GAME — the driver presses Down first. The observation carries a `NEW GAME:` line while the game has not started, and `go_to` now knows "Oak's Lab" and "Viridian Mart".
- Verified live from a blank cartridge: title → names (KYLE read back from SaveBlock2) → Squirtle → the rival fight → the parcel → the Pokédex, in about three minutes. Not done: an eval scenario that starts from the title, and a measured model-driven run.

### Added — `quest('copycat')`: Mimic from Saffron's Copycat (#278, the last gift)
- `quest('copycat')` buys the Poké Doll at the Celadon Dept. Store 2F when the bag has none (`shop(item=…)` machinery) and runs the existing Mimic tutor lesson. The issue called her TM and tutor; in FireRed/LeafGreen she
  only teaches the Mimic tutor move, once, for a Poké Doll. A Team Rocket grunt stands at her door until Silph Co. is cleared, so the beat needs `silph_co` (the driver says so and checks `FLAG_HIDE_SAFFRON_ROCKETS`).
- The other items of #278 (Dig from the Cerulean thief, the Dojo's Hitmon, Magikarp) were already scripted. Verified live: doll bought at the Dept. Store, Mimic learned, the beat reads done afterwards.

### Added — town services: `rename_pokemon` (Name Rater), `daycare`, and a TM shopping line (#277)
- `rename_pokemon(pokemon, nickname)` (agent/skills/services.py): travels to Lavender's Name Rater, answers his two Yes/No boxes, picks the party slot and types the name. A traded Pokémon or an Egg is refused by the
  game itself and reported. **Fix found on the way:** the naming keyboard is heap-allocated, so its text buffer is not always at the fixed catch-flow address (here 0x02004560; the fixed address held a stale nickname).
  `NamingDriver` now finds the struct through the game's own pointer statics (validated by the page byte and the buffer) and falls back to the old address.
- `daycare(action, pokemon)`: `deposit` leaves a Pokémon with the Route 5 Day Care man (another party member must still be able to fight), `withdraw` takes it back for ¥100 + ¥100 per level gained; both verified by the party count and the money.
- `team_report` gains a **TM shop** line: `knowledge/tm_plan.py` runs `tm_advice` over the Celadon Dept. Store 2F stock (TM05 / 15 / 28 / 31 / 43 / 45, prices from the decomp) and names the worthwhile TM per Pokémon with its price
  and whether you can afford it; TMs already in the case are skipped.
- Token caps raised for the two new tool schemas (overworld < 4800, everything < 5600). Verified live: rename on Lavender's real Name Rater, deposit/withdraw at the Route 5 Day Care; the existing catch-nickname and keyboard tests still pass.

### Added — `quest('articuno')`: the Seafoam Islands boulder puzzle (#264, second bird)
- `tools/gen_seafoam.py` → `knowledge/seafoam_data.py` (decomp): B3F's collision/elevation, the two fall holes, the four boulders and their hide flags, B4F's reveal flags and the stopped-current flag.
  `knowledge/seafoam_route.py` plans the pushes with the Victory Road solver (`solve(drop=True)`): any two B3F boulders sent through the holes reveal both boulders on B4F, and re-entering B4F swaps in the calm
  layout (`LAYOUT_SEAFOAM_ISLANDS_B4F_CURRENT_STOPPED`). The upper floors' boulder chain is NOT needed: B3F's boulder room is reached on foot (west door or B4F's ladder).
- `agent/skills/legends.py`: travel to B3F, push (one tile per push — a 20-frame press shoved the boulder two tiles and wedged one in the alcove), walk the holes/ladders-avoiding route, go down to B4F,
  surf to the platform, and hand the L50 Articuno fight to the model under the one-shot protocol. Shared `_engage_legend` with Zapdos; the beat sits before Sabrina and needs Surf + Strength.
- **Surf from the right tile**: the game offers Surf only from elevation-3 land, and Seafoam B4F's floor is elevation 4 almost everywhere (the prompt never appeared; `use_hm('surf')` gave up after six shores). `_surf` now tries elevation-3 shores first, and walking to a shore no longer re-enters the Surf search (it recursed).
- Verified live from Fuchsia: Route 19/20 → the cave → both boulders down → the current stops → Articuno in front of the model. Not done: Moltres (Sevii, post-game).

### Added — `quest('zapdos')`, and the router crosses water between regions of one map (#264, first bird)
- `agent/skills/legends.py`: `go_to('Power Plant')`, walk up to Zapdos (5,11), A through "Gyaoo!", and hand the L50 fight to the model under the one-shot protocol (state saved in slot 9). The
  beat sits before Sabrina in the chain and needs Surf; it is done by `FLAG_FOUGHT_ZAPDOS`. The driver waits for the battle intro to finish loading `gEnemyParty` before it reads the foe (it used to
  read the previous fight's Pokémon and the test's autopilot "fought" the legend).
- **Surf region links**: `tools/gen_regions.py` now flood-fills each water body and links the land regions of one split map that touch it (`SURF_LINKS`, e.g. Route 10: the Rock Tunnel side ↔ the
  Power Plant side). `route_to` has a third strict pass for them, `go_to` walks the `surf` step, and `unmet_gates` asks for Surf (and Cut, for the existing Cut-tree steps) instead of silently routing.
- `walk_to` while Surfing now plans over **water only** until the goal: the union grid routed along a shore tile, stepping on it ended Surf mid-crossing and the walk stopped with no path.
- Verified live: Lavender → Route 10 → Rock Tunnel → Surf across Route 10 → the Power Plant → Zapdos in front of the model. Not done: Articuno (Seafoam boulders) and Moltres.

### Added — one-shot encounters: Snorlax and the legends are caught, never knocked out (#272, the protocol)
- `knowledge/one_shot.py`: Snorlax, Articuno, Zapdos, Moltres and Mewtwo appear once. The battle observation now shows **ONE-SHOT: …** instead of the generic wild-battle line: the battle-start state is
  **auto-saved to slot 9** (once per encounter) — `load_state(9)` retries if it faints or flees — weaken it with the *gentlest* damaging move (named), stop at the red bar, status it, then
  `catch()` with the Master Ball (legends) or an Ultra Ball; no balls means reload and shop.
- **The autopilot no longer plays these fights**: `_auto_fight` returns at once for a wild one-shot foe and `quest('snorlax')` never passes its fight to it (it used to knock the Snorlax out). After the
  fight the quest says whether you actually caught it. Verified live on Route 12: the fight reaches the model, the protocol and slot-9 save are there, and a hit followed by `load_state(9)` restores full HP.
- Not done: the Route 16 Snorlax script (it ties into the Cycling Road / bike routing, #269), a "chip safely" damage estimate, and scripting the three birds' own encounters.

### Added — the Pokédex completion plan: a `DEX:` line in `team_report` (#266, first part)
- `tools/gen_dex_sources.py` → `knowledge/dex_sources.py` (from the decomp): `EVOLVES_FROM` (72 Kanto evolutions with level / stone / trade / friendship) and the seven in-game `TRADES` (Mr. Mime for Abra, Jynx for
  Poliwhirl, Farfetch'd, Lickitung, Electrode, Tangela, Seel — with the place). `knowledge/dex_plan.py` adds the curated one-offs (starters, Game Corner prizes, the Dojo Hitmons, Magikarp, Lapras,
  Eevee, the fossils, Snorlax, the legends) and ranks the missing species: wild (lowest-level spot first) → an evolution of something you own → a trade you can make → gifts/prizes → version exclusives.
- `team_report` ends with `DEX: 19/151 caught. Easiest next: Metapod — wild: Viridian Forest (grass L4-6); …`, with the quest that does it when there is one (`[quest('hitmon')]`). The status line shows `dex N/151`.
  `LeafGreenReader.read_dex_owned_ids()` reads the owned bits.
- Not done: completion targets (Kanto 150 / reachable / National), the National Dex scene, gating-aware sources, drivers for Eevee / fossils / the NPC trades.

### Added — the eight Gym beats are runnable: `quest('brock')` … `quest('giovanni')` (#260)
- `agent/skills/gymquest.py`: go_to the town, go_to('Gym'), then `challenge_leader` (its heal / save / lopsided-team warning stay there); a trainer on the way or the Leader ends the call as a
  battle for the model, and the same call resumes. A locked gym says what comes first ("Not yet — … first Silph Co.") instead of walking up to the guard. Verified live: from Pewter,
  `quest('brock')` walked in, warned once, fought the Camper and Brock and took the Boulder Badge.
- **Fixed**: the `parcel` beat counted only a `delivered_oaks_parcel` milestone, so a run from a post-parcel save (no milestone) had every gym beat blocked. `FLAG_SYS_POKEDEX_GET` (0x829) now counts.
- New `full_chain` eval scenario (post-parcel save → `hall_of_fame`), for running by hand. `quest()`'s listing now has a runnable script for every beat except the game start (`parcel`).

### Added — move tutors: `tutor(move, pokemon?, forget?)` (#274, mainland)
- **`tools/gen_tutors.py` → `knowledge/tutors.py`** (from the decomp): the 15 tutor moves, every species' tutor learnset (bit = tutor index) and the 12 mainland tutors — Route 4 (Mega Punch /
  Kick), Celadon (Softboiled), Dept. Store 3F (Counter), Cinnabar Lab (Metronome), Fuchsia (Substitute), Pewter Museum (Seismic Toss, ¥50 at the door), Rock Tunnel B1F (Rock Slide), Silph Co. 2F
  (Thunder Wave), Victory Road 2F (Double-Edge), Viridian (Dream Eater), Saffron Copycat's house (Mimic — needs a Poké Doll) — with map, NPC tile and the one-time `FLAG_TUTOR_*`.
- **`tutor`** (new tool): resolves the move loosely, picks the highest-level capable party member (or the named one; says who can't), travels, walks up to the NPC, and drives talk → YES → YES →
  the party screen → (a full moveset) the summary screen to forget a safe move. Verified live at Fuchsia: Venusaur into a free slot, Pidgeotto over Sand Attack; the lesson is one-time.
- **Bugs found live**: a Yes/No box can sit ON the party screen ("forget a move to learn X?") and must be answered before the cursor logic; and `_approach_adjacent` planned on the previous map's
  cached grid right after a warp/fly inside one agent step (it now refreshes first).
- Overworld token cap 4450 → 4500, "everything" cap 5100 → 5300 for the new tool.
- Not done: Sevii tutors, sourcing the Poké Doll for Mimic, paying the Museum fee on the way to the Seismic Toss tutor, and "which tutor moves are worth it for this team" suggestions in `team_report`.

### Added — fishing rods, the Bicycle and the Running Shoes flag (#269, first part)
- **Acquisition quests** (all verified live): `quest('old_rod')` (Vermilion house 1), `quest('good_rod')` (Fuchsia house 2), `quest('super_rod')` (Route 12's fishing house; reached
  from Fuchsia through Routes 15/12) — "Do you like to fish?" → YES; `quest('bike')` — the Pokémon Fan Club chairman's story gives the Bike Voucher, the Cerulean Bike Shop swaps it for the
  Bicycle. New optional beats (plus a guide-only `running_shoes` beat: the Pewter aide's scene is forced, `FLAG_SYS_B_DASH` 0x82F is the proof) and `go_to` map names.
- **`fish(casts?)`** (new tool): walks to the nearest shore, turns to the water and casts the best rod from the Bag (Key Items → rod → USE). From the decomp's fishing task: A is
  ignored during the dots and only a NEW press inside the 30-36-frame bite window reels in, so A is pressed every few frames until the cast ends — and never after (A facing water
  opens Surf's prompt). A wild Pokémon on the hook becomes a battle for the model; otherwise "no bite". Hooked a Magikarp at Vermilion on the second cast.
- **`use_item('Bicycle')`** mounts / dismounts (`is_biking` reads gPlayerAvatar.flags). `walk_to` gets off the bike first: a bike covers two tiles per press and overshot targets into doors
  (live-verified: it walked into the Cerulean Pokémon Center), and `use_hm('surf')` dismounts too.
- The overworld token cap in `test_tool_gating` went 4300 → 4450 for `forget_move` and `fish`.
- **Not done** (the rest of #269): running with B in the movement primitive (needs per-tile verification: doors, ledges, arrow tiles, stairs), bike-aware routing (the Cycling Road), the
  rod tier in the generated wild data for the dex plan.

### Added — Oak's Aide rewards and hidden items (#275, #276)
- **`quest('itemfinder')` / `quest('exp_share')`** (verified live): the Route 11 gatehouse (2F) aide gives the Itemfinder for **30 species caught**, the Route 15 one the Exp. Share
  for **50** (`knowledge/aides.py`); when short the quest says how many more to catch, and the Exp. Share is handed to the Pokémon that lags (`holder_for` + `give_item`).
  An `OAK'S AIDE:` observation line appears when a reward is claimable (or within 3 species). New optional beats `itemfinder`, `exp_share`; maps named for `go_to`.
- **Fixed — `quest('flash')` counted SEEN species** (#291): every aide script compares `VAR_0x8006`, which `GetPokedexCount` fills with the CAUGHT count, so Flash wants 10 caught.
- **Hidden items** (`knowledge/hidden_items.py`): `pick_up_items` now also walks to the worthwhile hidden items `area_facts` knows on the current map (PP Up, Rare Candy, vitamins,
  Max Revive / Full Restore, Ether / Elixir, Nuggets / Pearls / Star Piece / Stardust / Big Mushroom, stones, strong balls, TMs — not Potions or berries): beside the tile, FACE it, A.
  The Itemfinder is not needed once the tile is known. Collected (or empty) tiles are remembered in `ltm` (`hidden_taken`), unreachable ones are retried later.
- **Two bugs found live**: facing a WALKABLE tile — a tap steps onto it and A there does nothing — so the driver reads the player's facing (`read_player_facing`) and turns with a
  3-frame hold; and the game counts a species caught only when its owned bit and all three seen arrays agree (`live.set_dex` stages all four).

### Fixed — Cut trees in the region graph; Route 16's Fly house is reachable; the Poké Flute gate is narrower; Route 4's Magikarp house says why not (#293)
- **Cut-tree links** (`tools/gen_regions.py` → `BLOCKER_LINKS` in `knowledge/map_regions.py`): the generator still treats Cut trees / rocks as walls, but now also records the
  two regions each one separates. `route_to` tries a second strict search with those links (a `("cut", far-side tile, node)` step; `go_to` walks to the tile and `walk_to`
  cuts the tree) BEFORE the region-blind fallback, which used to plan Route 16's direct door (10,5) and skip the gatehouse.
- **Route 16**: Celadon → east strip → tree (41,11) → upper gatehouse (27,6)→(20,6) → house door (10,5) is planned and walked (and the way back). The Poké Flute gate on Route 16
  now applies only to routes that leave it by the SOUTH connection (the lower road the Snorlax guards): `Req.only_exits`.
- **`quest('fly')` is corrected** (it was wrong in the previous entry): no flute or Snorlax is needed, only Cut; verified live from Celadon, HM02 collected, and back.
- **Route 4**: the Magikarp house (and its 2F) joins the "ledges only go one way" `NO_WALK` rule, so from Cerulean's end `go_to` says there is no walking route (and what to do) instead
  of stalling; the errand helper reports that message. `quest('flash')`'s plan said CAUGHT where the game counts SEEN.

### Added — `quest('dig')`, `quest('hitmon')`, `quest('magikarp')` (#278)
- **`quest('dig')`**: the Rocket grunt behind the robbed house in Cerulean City (33,6) — beat him (hand-off or autopilot) and he returns **TM28 Dig** (flag 0x23F).
- **`quest('hitmon')`**: Saffron's Fighting Dojo — beat Master Koichi (trainer flag 0x63D), then take **Hitmonchan** from the ball at (7,3) (a one-time choice: Hitmonlee goes;
  flag 0x278); needs the Tea. The "nickname?" box is declined; a full party sends it to the PC box (the message says so).
- **`quest('magikarp')`**: the Route 4 Pokémon Center salesman sells a L5 Magikarp for ¥500 (flag 0x249; nickname declined). Verified from Pewter; from Cerulean's side
  `go_to` stalls at the east end of Route 4, so the beat text says to do it on the way to Mt. Moon. The map is named `Route 4 Magikarp House` because `go_to` reads any
  destination containing "pokemon center" as "the nearest Center".
- `_gift_errand` gained `answers` (the Yes/No answers in order) and hands a trainer fight back; new optional beats `dig`, `magikarp`, `hitmon` in the chain.
- Not done: Copycat's house — in FRLG she needs a Poké Doll and teaches the Mimic *tutor* (not a TM), which belongs with the move tutors (#274).

### Added — `quest('flash')` and `quest('fly')` (#268)
- **`quest('flash')`** (verified live): travels to the Route 2 east building, talks to Prof. Oak's Aide and takes HM05 once 10 species are SEEN (it says how many you have
  seen when short). New map names `Route 2 East Building` / `Route 16 House` for `go_to`. A shared `_gift_errand` does travel + talk + advance until the flag is set.
- **`quest('fly')`** says what is missing before it travels: the Poké Flute, then the **sleeping Snorlax** — the house is on Route 16's far WEST end, behind it (Celadon's
  exit lands on the east end); the issue's "needs Cut" was wrong. Once the Snorlax is gone (`FLAG_HIDE_ROUTE_16_SNORLAX` 0x080) it runs the same errand (HM02, 0x238).
- **Not working yet**: the walk to that house. `go_to`'s strict region graph treats Route 16's Cut tree at (41,11) as a wall, falls back to the region-blind graph and
  plans a direct door (10,5) that skips the gatehouse (27,13)→(20,13) both halves need. Waking the Snorlax itself is #272.

### Added — money targets, supply checks and earning advice for the story beats (#270, #271)
- **Supplies** (`knowledge/beat_readiness.py`): each beat now also wants a number of HP items and Revives in the bag (Victory Road 10 + 3, the League 12 + 4…).
  `quest('<beat>')`'s warn-once gate names the shortfall ("2 Potions / Restores in the bag (10 recommended)"), and the plan and the `quest()` listing show the
  recommendation (`[rec. L42+]`).
- **Money** (`knowledge/money.py`): a yen target per beat (League ¥20000, Victory Road ¥9000…) and `earn_advice` — sell treasure first (`shop(sell=true)`), Pay Day if a
  party member knows it, else trainer prize money (wild Pokémon pay nothing). A `MONEY:` line appears in `team_report` and under `STORY NEXT` in the observation
  when the next costly beat wants more than you hold.
- **League prep** now sells treasure and buys supplies with the budget: Revives to the recommended count first, then Full Restores (`supply_purchases`). The Indigo
  Plateau's Pokémon Center has a clerk, so `shop` / `sell` work there (`_at_a_shop`).
- **Fixed**: `sell` opened the bag on the pocket used last — at the Plateau the empty Poké Balls pocket, where A on "Cancel" closed the bag — so it now switches to Items
  first; and the Poké Mart "Potion → substitute" table listed item 24 (a **Revive**) as a Hyper Potion (it is 21).
- Not yet: Game Corner coins / repeatable trainers as scripted income (#270's remaining idea), Dept. Store TM planning (#277).


### Verified — the League's loss path and the credits, live (#259 follow-up)
- **Loss** (`test_a_league_loss_resets_the_rooms_...`): losing in Agatha's room heals the party, takes money (¥14,044 → ¥5,524 in the staged run), clears all five
  `FLAG_DEFEATED_*` and respawns at the Plateau's Pokémon Center; `quest('elite_four')` then goes back in from Lorelei. No reload is needed (main's blackout handler
  would reload the pre-door save, slot 3, first).
- **Credits** (`test_the_credits_end_in_a_soft_reset_...`): after the Hall of Fame the game returns to Indigo Plateau and rolls the credits for ~14,000 frames, then
  SOFT-RESETS to the title screen (RAM empty for a moment — party 0, map 0/0 — then the attract-mode loop forever). The battery save holds the cleared game and
  `drive_into_gameplay` (Continue) lands in **Pallet Town** with 8 badges and `FLAG_SYS_GAME_CLEAR` — a valid post-game start for the post-game issues.
- **Fixed**: `main()`'s end condition fired at step 0 for any run that started after the game was cleared (a post-credits save, or a `logs/progress.json` kept
  from an earlier run). The goal is now "the Hall of Fame milestone was recorded during THIS run".

### Added — `quest('elite_four')`: the Pokémon League, start to Hall of Fame (#259)
- New `elite_four` beat after `victory_road` and `agent/skills/league.py` (`LeagueMixin`). From Indigo Plateau it PREPS before the first door (heal, `shop`, a save to
  slot 3), walks in through the Center's north door and then, room by room (Lorelei, Bruno, Agatha, Lance, the Champion; maps/positions/flags from the decomp's
  `PokemonLeague_*`): waits out the forced walk up, stands in front of the leader, faces and talks, hands the battle to the model (or autopilot with `auto_trainers`),
  and walks through the exit once the leader's defeated flag is set. It resumes from whatever room it finds itself in. The readiness gate asks for a best Pokémon of L54+
  and five at L46+.
- **Done**: `FLAG_SYS_GAME_CLEAR` (0x82C, set in the Hall of Fame) records the new `hall_of_fame` milestone (also from `main._apply_progress`, so winning by hand counts) and
  `main()` now ENDS the run on it (`goal="hall_of_fame"`). New `elite_four` eval scenario (fixture `saves/live/league_door.ss1`, see `tests/live/README.md`).
- **A loss** (from the decomp, NOT yet verified live: `DoWhiteOut` → `EventScript_ResetEliteFourEnd`) clears every defeated flag, heals, takes money and respawns at the Plateau's Center; the quest
  simply starts over, and `main`'s blackout handler reloads the pre-door save (slot 3) first.
- Live-verified end to end (all five rooms and the Hall of Fame in ~2 minutes with one-hit foes). Not verified: what the credits do to the native backend; the run
  ends when the milestone is recorded, before them.

### Added — `forget_move`: the Move Deleter in Fuchsia City (#273)
- HM moves can't be forgotten at the normal prompt, so a party with four HM moves was stuck. `forget_move(pokemon, move)` travels to the Move Deleter (Fuchsia
  City house 3, now `go_to("Move Deleter's House")`), drives his dialogue → the party screen → the summary screen → "forgotten completely?" and confirms the
  move is gone. It keeps the party's last copy of an HM (Cut / Surf / Strength / Flash / Fly) unless `force=true`, and says so for an unknown move or a Pokémon's
  last move. `teach_move`'s "HM move — can't be forgotten" now points at it.
- Two traps found live and guarded: the summary screen passes through a loading callback (0x08135C0D) where an A acts on row 0 — the driver waits unless the field
  callback is up — and SUMMARY_MOVE_CURSOR is stale until the first key. The driver also stops the moment a move other than the target disappears (an
  earlier draft deleted Cut, Surf and Strength this way).
- Not yet: "HM slave" planning (keeping HMs on a dedicated party member / PC-swap logic).

### Added — `shop(sell=true)`: sell treasure at a Poké Mart (#270, first part)
- The Mart driver could only buy. `shop(sell=true)` now sells every spare treasure in the bag (Nugget ¥5000, Star Piece ¥4900, Big Pearl ¥3750, Big Mushroom, Stardust,
  Pearl, Tiny Mushroom), or `item` / `quantity` of a named item. Stones, vitamins / Rare Candy, healing and status items, Repels, Escape Rope and Poké Balls are protected
  (`knowledge/selling.py`). Flow (live-verified): clerk → SELL → the bag in shop mode → A, A, A per unit; one unit at a time, re-aiming the cursor at the item
  before each, because a spare A after a stack empties sold the neighbouring items. `_open_buy_menu` gained a `sell` option.
- Not yet: a money target per milestone, earning plans (Game Corner, repeatable trainers), and showing money against the next shopping list in `team_report`.

### Changed — the free switch is taken automatically so the ace stops hogging trainer XP
- With Battle Style SHIFT (#283) the model was only *offered* the free switch and, in autopilot fights, never saw it. `_battle_settle` now answers the
  trainer's "Will you change POKéMON?" itself when the Pokémon on the field is not lagging and a teammate more than 7 levels under the top is healthy
  (>= 60% HP) and within 4 levels of the toughest Pokémon the trainer has left (`knowledge.party.pick_shift_trainee`; the strongest such teammate is picked).
  The result says so and how to swap the ace back; boss fights whose Pokémon outclass the team are left alone. Applies to model-driven and autopilot fights.

### Added — readiness gates for the non-gym story beats (#271)
- `knowledge/beat_readiness.py`: a recommended-strength table (best Pokémon level + how many at a floor level) for `rocket_hideout`, `pokemon_tower`, `snorlax`,
  `silph_co`, `pokemon_mansion` and `victory_road`, from the level ranges of their trainers and wild Pokémon. `quest('<beat>')` now warns **once** when the
  party is short ("only 1 of your team is L34+ … grind() with no level lifts the weaker members, then heal() and shop()"); the next call goes ahead, and a
  resumed driver is never re-warned. The beat's plan (`quest` on a guide beat) also prints the recommendation. Elite Four prep (#259) and the full-chain eval (#260) can reuse the table.

### Added — Battle Style SHIFT: a free switch after a trainer's Pokémon faints (watched run: the ace out-levelled the team by 8+)
- The agent now pins the game's **Battle Style** option to SHIFT (`BATTLE_STYLE=shift` default, `set` or empty to leave it; `game/options.py` writes SaveBlock2
  every step). With SHIFT the game asks "Will you change POKéMON?" before a trainer's next Pokémon comes out — a switch that costs **no turn**.
- `use_move` / `advance_dialog` stop at that box **once** and tell the model: "FREE SWITCH: … Bananas (L22) trails — switch_pokemon('Bananas')", naming the
  strongest healthy laggard when the mon on the field is at the top level. `switch_pokemon` then answers YES, picks the mon and returns "FREE switch";
  any other action answers NO. The box is recognised by the battle script pointer (`gBattlescriptCurrInstr` 0x02023D74 sitting on the `yesnobox` at 0x081D872B).
  Autopilot fights (go_to / grind / hideout) still decline it. New `LeafGreenReader.read_enemy_party()` counts what the trainer has left.

### Fixed — grind() shuttled Route 11 <-> Route 9: the Cut planner ignored ledges (a watched run)
- Route 9's grass sits east of a Cut tree **and** behind a one-way ledge. `_cut_through` planned without ledge hops, so it found no route, never cut the tree and
  `walk_to` answered "No walkable path" while `_reachable_tiles` (which hops ledges) said the grass was reachable — so `grind` relocated to Route 9 across the
  whole map, gave up, and was sent back to Route 11, six times in a row. `_cut_through` now plans with ledges and elevation like `walk_to`, and a
  "No walkable path" on the grass target counts as a strike in `_failed_grass` (two strikes drop the route for the session).

### Fixed — grind() stranded at Route 4, a 100-minute Route 21 loop, a silent quest, stale walk_to bounds (two watched runs)
- **Route 21 loop**: `grind(20)` from Pallet picked Route 21 (open water, wild L17-28) 14 times in a row, each call pacing Pallet for 100 game-minutes.
  Both Route 21 maps are now gated behind Surf, and a grass route that `go_to` failed to reach twice (`_failed_grass`) is dropped for the session.
- **Route 4 pocket**: healing at Route 4's Mt. Moon Pokémon Center exits into a west pocket one step from Route 3, but `NO_WALK` (meant for the Cerulean-side
  ledges) said Route 3 / Route 2 / Viridian Forest were unreachable, so `grind` walked the party round to Route 22 (wild L2-5, almost no XP). `NO_WALK` is
  now region-aware (`ok_regions`), and `grind`'s relocation skips any route `NO_WALK` rules out instead of trying it. `_reachable_tiles` also hops ledges like `walk_to`.
- **Misleading hint**: "Why the closest grass was skipped" showed whichever gate was seen last (the SS Ticket one). The reasons now reset per search, name the
  route ("Route 24: …"), and list up to three.
- **`walk_to` bounds check** used the previous map's size when called after a tool that changed maps in the same step (`(10,10)` "outside" a 15x10 Center while in Vermilion); it now refreshes first.
- **`quest('ss_ticket')`** looped 12× in 0.03 s and said only "Didn't reach Bill's Sea Cottage yet" when `go_to` made no progress (e.g. the rival gate); it now returns `go_to`'s reason.

### Fixed — grind() kept walking into Cerulean's rival ambush (a watched run)
- With the ace at L17-19 and the rest of the team far behind, `grind()` relocated to Route 24 (the grass that fit the trainees), whose only way in is
  Cerulean's north exit — where the rival ambushes you (Pidgeotto L17, Abra L16, Rattata L15 and a starter L18 that counters yours). The relocation's
  autopilot fought him, lost, healed, and tried again, while the model was told "no tall grass is reachable" / "Couldn't reach tall grass" and believed it
  was grinding. Three causes, three fixes:
  - **A gate for the ambush**: `knowledge/gates.py` has a new `level` requirement; Route 24 needs the party's best at L21 until the scene is over
    (`FLAG_GOT_FAME_CHECKER`). `go_to` and `grind` honour it like every other gate, and the hint says how to fight him by hand.
  - **Truthful messages**: when grind skips the nearest grass (a gate, or a trainer that beat us) the failure message now says why.
  - **Lost routes are remembered**: a grass route whose way in beat us is skipped across `grind()` calls until the best Pokémon is 3 levels higher
    (it used to be forgotten each call), and a travel-battle loss is recorded where the trainer stood, not at the Pokémon Center after the blackout.

### Added — `quest('victory_road')`: Viridian → Route 22 → Route 23 → Victory Road → Indigo Plateau (verified end to end on the real ROM)
- The road to the cave is plain `go_to` (Route 22's rival, Route 23's eight badge guards, the Surf crossing — Route 23's middle is a river, the old text said
  Surf wasn't needed). Inside, `knowledge/boulder_puzzle.py` is a push-based Strength-boulder solver (one search state = boulders + pressed switches + the
  region the player can walk) and `knowledge/vr_route.py` plans the cave's order of play from decomp data (`tools/gen_victory_road.py`):
  1F's switch boulder (19 pushes) → 2F's west switch → 3F: drop the boulder down the hole (it reveals 2F's second boulder) and follow it → 2F's second
  switch → the 3F side room → 2F's east exit at (48,12) → `go_to` Indigo Plateau (`FLAG_VISITED_INDIGO_PLATEAU`).
- Things the live ROM taught: the cave is split into elevation levels (a step between two non-zero levels is refused — and so is a push, since the push is a
  step into the boulder's tile); arrow warps (the 1F entrance, the 2F exit) only fire with their arrow held, so a stand ON one is a manual step and never a
  `walk_to` destination; every floor load puts its boulders back (pressed switches stay pressed; Route 23's transition resets the lot); the game only reports
  objects near the camera, so the driver remembers boulders; 2F's (33,19) boulder is hidden until the 3F one falls.
- Double battles: Victory Road 3F's Ray & Tyra open with a party screen the old code treated as a stray menu (B cannot cancel it). `forced_party_screen` now
  looks at our second battler in a double battle, and `_send_next_mon` brings in a benched Pokémon.
- Test staging: `live.strong_lead()` / `live.boost_party()` (the fixture party is far under the cave's L40+ wilds).

### Changed — hardened nickname driver, with a varied pool of ideas
- `knowledge/nicknames.py`: a pool of 211 typeable, ≤10-character names that have nothing to do with the species (dad jokes, food, pets, titles, objects,
  places: "Zap Daddy", "Hobbes", "Waffles", "Sir Wiggle"…), `suggest()` (a fresh draw that skips names already on the team), `pick()` and `usable()`.
  The wild-catch / Safari hints now show three of them, and a refused pick (no ball spent) lists four to take or remix. A pick that is empty after
  the clean-up, a duplicate or has fewer than two letters/digits is replaced by a pool name instead of reaching the keyboard.
- `game/naming.py`: the keyboard page is read from the game's own struct (`NAMING_PAGE`, `currentPage`), not counted with a blind Select tally;
  `clear()` and `abort()` (empty box + OK keeps the default name) so a failed typing run can always leave the screen.
- `_give_nickname` never strands a catch on the keyboard: the Yes/No is declined if the screen never opens, an untypeable pick is retried with a
  pool name, and if nothing can be typed the screen is left with the default name.
- Tests: pool invariants, fake-keyboard desync / abort / fallback cases, and a live mixed-case "Zap Daddy" catch that checks the RAM page read.

### Added — `quest('silph_co')`: the Card Key, the Lapras, Giovanni and the Master Ball
- Silph Co. is 11 floors joined by stairs and teleport pads, with 20 card-key doors. `tools/gen_silph.py` turns the decomp's map collision, warps and the
  `Close<N>FDoor<K>` scripts (the doors are closed on map load while their `FLAG_SILPH_<N>F_DOOR_<K>` is clear) into `knowledge/silph_data.py`;
  `knowledge/silph_route.py` searches floor × tile, with a shut door costing an "unlock" (face it, press A, needs the Card Key).
- `agent/skills/silph.py` executes the plan's first action and re-plans, in order: the Card Key (5F item ball) → the Lapras worker on 7F (NO to the
  nickname) → Giovanni (stepping on 11F (5,15)/(6,15) starts the scene) → the President's Master Ball. Resumable like the other quests.
- Silph Co.'s door is guarded by a Rocket until Mr. Fuji is rescued (`FLAG_RESCUED_MR_FUJI`): the beat now needs `pokemon_tower`. Verified end to end on the
  real ROM (Card Key → Lapras with the rival's 7F trigger → Giovanni → Master Ball); the live test boosts the fixture party's stats (`live.boost_party()`).

### Added — the puzzle gyms reach their Leader (verified on the real ROM: Viridian, Fuchsia, Saffron, Cinnabar)
- `challenge_leader()` now solves what stood between the model and the last four Leaders:
  - **Saffron / Sabrina**: 30 teleport pads, each warping to a partner pad of the same map. `knowledge/gym_pads.py` (decomp data + a BFS where a step onto
    a pad is a teleport edge) plans the chain; `walk_to` takes an avoid-set so a walk never crosses a pad by accident.
  - **Cinnabar / Blaine**: six quiz machines (correct answers from the decomp: YES NO NO NO YES NO, pressed from the tile south of the machine). The rules
    are five fixed A presses; pressing A while the QUESTION prints skips to its end and the next A takes the default YES ("Bad call").
  - **Viridian / Giovanni** (spinner maze) and **Fuchsia / Koga** (invisible walls = real collisions) needed nothing new: `find_path_spin` and the live grid.
- Test staging: `live.defeat_all_trainers()` (flags 0x500..0x7E6) for navigation-only tests.

### Added — `quest('pokemon_mansion')`: the Secret Key (verified end to end on the real ROM)
- The Mansion's barriers hang on ONE global statue switch (`FLAG_POKEMON_MANSION_SWITCH_STATE` 0x26C): `tools/gen_mansion.py` turns the decomp's
  `PressSwitch_<floor>` scripts, map collision and warps into `knowledge/mansion_data.py`; `knowledge/mansion_route.py` solves floors × switch state
  by search; the driver executes the plan's first action, re-reads the real state and re-plans (a trainer or a dropped input costs one re-plan).
- Things the live ROM taught: statues are pressed from the tile SOUTH of the statue facing up (`BG_EVENT_PLAYER_FACING_NORTH`); only warp tiles
  with a door / stairs / arrow / fall behaviour fire (the other warp events are LANDING spots — stepping on 2F (27,17) does nothing); stairs are
  directional (stand on the tile and hold its button — `walk_to` would "nudge" off it); 3F's holes drop you to 1F.
- `go_to` to Cinnabar after flying there no longer demands Surf (`FLAG_VISITED_CINNABAR` meets the gate).

### Added — scripts for the Lavender story: `quest('pokemon_tower')`, `quest('poke_flute')`, `quest('snorlax')` (verified end to end on the real ROM)
- **Pokémon Tower**: the climb to 7F (ghost wilds and Channelers are handed to the model like any quest battle; the rival's 2F trigger and the
  6F Marowak ghost play out), the three Grunts' sight-line fights, then Mr. Fuji at (11,4) — he sets `FLAG_RESCUED_MR_FUJI` and warps you to his
  house. Needs the Silph Scope.
- **Poké Flute**: Fuji at (3,3) in the Volunteer Pokémon House. **Snorlax**: Route 12 is cut in two by a gate house (in at (14,15), out at the
  south door (5,11)); then the long walk to (14,69), the Poké Flute prompt (YES) and the level-30 fight (`FLAG_WOKE_UP_ROUTE_12_SNORLAX`).
- Test staging: `live.fly_to(town, flags=, key_items=)` and `live.give_key_item(id)` in the live harness.

### Added — the whole main story as a guided chain, start to Elite Four
- **`knowledge/story_beats.py`**: ~30 ordered beats (Oak's Parcel → … → Victory Road) each with where / what must come first / how it is DONE
  (flags, key items, badges and milestones, verified against the pokefirered decomp) / numbered steps. `quest()` lists the chain
  (✔ done / ▶ next / … blocked, scripted ones marked); `quest('pokemon_tower' | 'poke_flute' | 'snorlax' | 'silph_co' | 'pokemon_mansion' |
  'koga' | 'sabrina' | 'blaine' | 'giovanni' | 'victory_road' | …)` prints a state-aware plan ("not yet: first X") when there is no script yet.
  The observation shows `STORY NEXT: …` (after the first badge). Replaces the six-entry `knowledge/quests.py`; `quest`'s name is a free string.
- **`quest('tea')`** (new script): the old woman in Celadon Mansion 1F gives the Tea; the Saffron gate guard then lets you in. The gate hint
  used to send the model to "the Celadon Mansion roof / Game Corner"; the gates now point at the right quests and Saffron's gate is met by
  `FLAG_GOT_TEA` (the guard consumes the item).
- Fixed `_probe_warp` on doormats with two warp tiles where only one fires (Route 7's gate house: (11,5) works, (11,6) does not — go_to stalled
  there forever); it now tries the neighbouring warp tiles of the mat.

### Added — `quest('rocket_hideout')`: the Silph Scope (verified end to end on the real ROM)
- The whole story beat after Erika, scripted and resumable: the Game Corner Grunt + poster switch → Rocket Hideout B1F → B2F → B3F →
  B4F; the west half's Grunt and the Lift Key; the elevator (panel list driven by hand, door (2,5)); the two door Grunts that open the
  barrier; Giovanni and the Silph Scope; the elevator back to B1F, the south-wing Grunt that opens that barrier, and out to Celadon.
  Records `got_silph_scope`; `auto_trainers=true` fights the trainers on the way.
- **Spinner mazes** (`game/pathfinding.find_path_spin`, `tilemap.spin_map/spin_stops`): an arrow tile carries the player in its direction
  across PLAIN floor too (turning on further arrows) until a stop tile or a wall — verified live (B3F's maze is the only way to B4F). `walk_to`
  avoids arrow tiles while a way round exists, plans the slides when there is none, waits out each slide and replans if one ends elsewhere.
  Reusable for Silph Co. and Viridian Gym.
- Fixed `_probe_warp` walking the NEW map to the old map's stand tiles when the first walk already stepped through the warp (it put the
  hideout run on the wrong side of B2F).

### Fixed — third unwatched run (200 steps: Erika beaten, team L32 vs the ace's L38 — the ace gap is closed)
- **Futile level-target grinds.** After Erika the model called `grind(42)` at L38 and spent ~700 s on Route 7/8 (wild L17–22): the ace
  gained nothing. `grind(level)` now refuses up front when the best OPEN (un-gated) grass tops out 12+ levels below the Pokémon, and
  says what to do instead; the READINESS gym line no longer suggests `grind(N)` for an ace ≥ L30.
- **Pointless shop trips.** 13 heal→shop visits at ¥600 "bought nothing" (the Dept. Store's cheapest ball / potion costs more) while READINESS
  kept saying `shop()`. `shop()` now says what it costs and the need stays quiet until the money grows (`ltm.data["shop_broke_at"]`).

### Fixed — `use_item` in battle after a switch
- `use_item` judged success by party slot 1's HP, but the item goes to the ACTIVE battler, which after a switch or a forced
  replacement is someone else: a heal that landed was reported "Couldn't use the Super Potion — you're back in the battle" (twice
  in one watched run, each costing a turn). It now tracks the active battler (`gBattleMons[0]` HP, matched party mon for status and
  name) and reports "X is already at full HP — the Potion would do nothing" instead of mashing A.

### Fixed — shopping in Celadon City
- `shop()` from Celadon routed to Saffron's Mart ("gate guards want Tea") and a run sat at 0 Poké Balls with ¥3044: the Celadon Dept.
  Store was not a mart waypoint. Its 2F items clerk is now one (`MAP_KIND[(10, 1)] = "mart"`), `shop()` walks to the clerk that sells
  the most of the plan (from the map, not a standard Mart's fixed tile; `_clerk_approach` is shared with `shop(item=…)`), and since
  the store sells no Poké Ball / Potion it buys the next grade up with the same budget (Great Balls, Super / Hyper Potions).

### Fixed — what a second unwatched Gemma run turned up
- **A blackout reset the whole game.** `_handle_blackout` reloaded `saves/slot_0.ss1` — a file from July that survives between
  runs — which put the run back on the new-game naming screen (party gone, 75 steps wasted typing names). Only a slot saved by
  THIS process counts now (`saved_this_session` / `latest_session_slot`); the blackout handler reloads the most recent one (the
  pre-gym `save_state(1)`), or plays the whiteout when there is none, and the `load_state` tool refuses a slot this session never saved.
- **PC duplicates.** The catch policy only checked the party for "already have one", so the run caught 8 Meowth, 5 Pidgey and 5
  Bellsprout (45 stored mons, 11 of them Spearow), blocking the autopilot (every foe was "worth a ball") and burning all its balls.
  `evaluate(..., stored=)` now refuses a species already in the PC and says to `pc('swap')` it in.
- **Gym retries.** A blackout inside a gym is recorded (`ltm.data["gym_losses"]`, team level total); `challenge_leader` refuses to walk
  back in until the total has grown by 8 levels — the run had challenged Erika three times with the same lopsided team.

### Fixed — Route 8 ping-pong, and a team that never catches up (watched run)
- **Walled-off grass.** Route 8's tall grass is a pocket sealed by two Cut trees. `grind` aimed for the nearest grass by distance;
  `walk_to` counted the trees as NPCs, "engaged" one, then the other (the bounce), and the run left for Route 10 and came back.
  Now `walk_to` cuts the tree that is the only way through (and says so when it cannot Cut), trees are never "engaged",
  `grind`'s grass target must be reachable (Cut trees count as open only if the party can Cut), and a map whose only grass is
  sealed is remembered and skipped.
- **Ace out-levelling the team (~2×).** `grind()` that balances the team played every wild fight through the LLM (~30 s and ~60k
  tokens each), so the trainees gained about one level in 15 minutes. A balancing session now autopilots boring fights by default
  (12 per call; `auto_battles=0` restores the old behaviour, a level-target grind stays model-driven).

### Fixed — forced-switch dead end (unwatched Gemma run, 200 steps)
- After the active Pokémon fainted the game's forced "Choose a POKéMON" screen reads as TRANSITIONING, and the observation said
  "dialog/transition not advancing — press A". Pressing A on the fainted lead only shows "has no energy left to battle!", so the
  run spent its last 319 tool calls (40% of the run) pressing A / waiting. Now the observation says `FORCED SWITCH … call
  switch_pokemon(...)` (with the party-vs-foe roster), `press_button` / `advance_dialog` on that screen point at `switch_pokemon`
  instead of pressing, and `switch_pokemon` first dismisses the "no energy" message (it blocked the cursor and made the switch fail).

### Added — sharper battle advice (watched-run follow-up)
- `Foe` read from the live battler (`gBattleMons[1]`: real moves, Speed, Atk/SpA, ability) via `read_foe_battler()`.
- The `Party vs …` roster now uses the foe's KNOWN moves (not just its types), shows who outspeeds whom, and flags
  absorb/immunity abilities (Levitate, Volt/Water Absorb, Flash Fire) so those moves count as ×0.
- `Low HP:` line when the active mon is under ~⅓ HP, or ≤60% and the foe's best hit (Gen III formula) would KO it: finish a
  nearly-dead foe, switch (the only save from a KO), heal only with an item that survives the hit, or flee a wild foe.
- `switch_pokemon` accepts the `Nickname(Species)` labels the roster prints.

### Fixed — the model sent out fainted Pokémon and misread type matchups (watched run 20261117-141900)
- **The battle observation named the wrong Pokémon.** `Lead:` was always party slot 1, so after a switch a fainted Ivysaur showed as
  `HP=0/50 (healthy)` while Kakuna fought, and the model tried to switch it back in six times. In battle it now reads `Active: …` (the mon
  actually fighting, `FAINTED` when it is down). The same slot-1 mistake fed the wrong *types* into STAB (Kakuna's Poison Sting was scored with
  Ivysaur's Grass/Poison) and the wrong HP into the low-HP warning; both now use the active battler.
- **Party-vs-foe line in every battle** (`knowledge/matchup.py`): every slot as `FAINTED` / `ACTIVE` / HP, and for each living teammate its best
  move's multiplier against this foe and how hard the foe's own types hit it. A `Better matchup: switch_pokemon('X') — …` line appears only when
  the active mon is badly placed (its best attack resisted/immune, or the foe's STAB is super effective on it) and a healthy teammate clearly
  beats it (no needless free hit).
- **`switch_pokemon` refusals list the options** ("Can switch to: 4:Sky High(Pidgey) (7/22)") instead of a bare "has fainted".

### Changed — system-prompt token trim (~1.4k tokens per call early, more with vision off)
- Sections are shown only when they can matter: Game Corner from 3 badges, Safari Zone from 4, the Brock gym-prep section at 0 badges only,
  and the Screenshot / Overworld-orientation sections only with `USE_VISION=true`. The raw battle-menu grid (which `use_move` drives) became
  a two-line PP rule. Decision priority #5 now points at the new `Party vs …` / `Better matchup:` lines.

### Fixed — four things a watched grind run showed (run 20261117-133255)
- **grind no longer plans around closed roads.** Relocation picked Route 4, 24 and 25 (all behind Brock's gate), stopped "gated" 18 times,
  spent its three attempts and then claimed there was no grass anywhere. Gated candidates are now skipped up front without using an attempt
  (`_grass_route_gated`), so it goes to grass it can actually reach.
- **A nearly-fainted Pokémon is told to switch.** The fresh L3 catches that "lead first" fainted four times in 17 ticks because the model kept
  attacking. After every move, an active Pokémon at or below 35% HP with a fit teammate gets `⚠ X is at 3/16 HP … switch_pokemon('Y') now, or use
  a Potion` (`knowledge.party.low_hp_switch_hint`, works in every battle).
- **grind's battle message lists the active Pokémon's moves** ("BananaBiff knows: Scratch, Leer.") — eight calls went on `use_move('Tackle')` after
  the lead changed to a Pokémon that doesn't know it.
- **grind() mid-battle is refused** ("That battle is still going…") instead of starting and counting a second battle, and the battle-start message
  now lets the intro settle before reading the foe (it used to report the previous foe at 0 HP).
- Tests: gate-aware relocation, the yield text, the switch hint, the mid-battle refusal and its resume. Two live tests were updated to the new
  realities (a badge-less fixture can no longer relocate to Brock-gated grass; the grind helper plays on after a refusal).

### Fixed — the Pewter "Follow me!" loop (regression seen in a watched run)
- Heading east out of Pewter City before Brock is beaten makes the Gym Guide walk the player back to the gym door, every time. `go_to('Route 4')`
  and `grind`'s relocation treated the road as open, spent their hop budget bouncing off him and ended with "trip … ended: budget". The route is
  now gated on the Boulder Badge (read from the GAME's badge byte, not from memory, so a stale belief can't open it): `go_to` stops up front with
  the reason and what to do (beat Brock), and grind skips that grass. A Pewter City area note says the same on arrival.
- Test: a live regression (`go_to('Route 4')` from Viridian Forest with 0 badges) and a gate unit test.

### Added — the Celadon Game Corner: coins, the Prize Corner and the slot machines (#215)
- **`quest('coin_case')`** gets the Coin Case from the man in the Celadon Restaurant.
- **`game_corner(action, amount)`**: `status` (coins, prices), `buy_coins` (the clerk's 50 / 500 lots, ¥20 a coin, checked against money and the
  9999-coin cap) and `slots` (N full-bet spins).
- **Prizes via `shop(item=…)`**: TMs (13, 23, 24, 30, 35), battle items and the Pokémon (Abra, Clefairy, Pinsir, Dratini, Porygon) are paid for in
  coins at the right clerk, from the decomp (`tools/gen_game_corner.py` → `knowledge/game_corner_data.py`, LeafGreen side of every `.ifdef`).
  Not enough coins gets the arithmetic ("2800 more = ¥56000, or win them"). A prize Pokémon's nickname box is declined; the result says
  whether it landed in the party or the PC.
- **The slot driver is a port, not luck** (`knowledge/slots.py`, from `slot_machine.c`): each spin the machine rolls a hidden *bias* (7 about 6% of
  the time, and a Rocket / 7 bias sticks until it pays) and a reel press slides the reel up to four positions to serve it if it can. The driver
  finds the machine's state block in memory (reel positions, sub-pixel, bias), replays `StopReel1/2/3` for each future frame and presses A in
  the middle of a window of good frames, then waits for exactly the coins the stopped reels pay. Measured on the real ROM: +2,400 to +3,900
  coins per 150 spins (8–13 jackpots of 300), against the −3 coins a blind spin costs. A stop-loss (300 coins) ends a bad session.
- Menu handling lessons recorded in code: the clerks' list ignores input while it fades in (probe before pressing A again), closing text is
  dismissed with B only (A on the field talks to the clerk again — and buys again), and the coin counter now counts as "progress" for the
  watchdog.
- Tests: `tests/test_game_corner.py`; live tests drive the Coin Case quest, coin buying, a TM and a Pokémon prize, and a 12-spin slot session.

### Added — area guidance for every dungeon, puzzle gym and late-game stretch (#240)
- **`knowledge/area_guide.py`**: a goal / what-to-watch-for / tip for 23 areas — Mt. Moon, Rock Tunnel, Diglett's Cave, the Power Plant, the Pokémon
  Mansion, Seafoam Islands, Victory Road, Cerulean Cave, the Safari Zone, the Rocket Hideout, Silph Co., the Pokémon Tower, the S.S. Anne, the four
  puzzle gyms (Sabrina's warp pads, Koga's invisible walls, Blaine's quiz machines, Giovanni's spinner tiles), Routes 12-15, the Cycling Road, Saffron's
  gates and the Underground Path, the sea route to Cinnabar, Routes 22-23 / the Plateau, and the Elite Four — 98 maps in all. Every dungeon floor
  the game names has one (a test checks).
- **Facts come from the decomp** (`tools/gen_area_facts.py` → `knowledge/area_facts.py`): each map's trainer count, item balls (the item read from the
  script that gives it) and hidden items with coordinates, and — for Sabrina's gym — the warp-pad pairs. The Card Key (Silph Co. 5F) and the Secret Key
  (Mansion B1F) are named where they lie. Claims the decomp contradicted were fixed on the way (Moltres is on Mt. Ember in this version, the Tea is
  free from the Condominiums woman, Silph's Lapras comes from a 7F employee).
- **Shown in the observation** (`AREA — Victory Road: …`) on arrival and as a reminder every 25 ticks while the player stays on a covered map.
- Not part of this change: automatic solvers for the puzzle gyms (Sabrina's pads, Koga's walls, Blaine's quiz, Giovanni's spinners) and the Seafoam
  boulder puzzle — the text tells the model what the obstacle is; a solver is a separate piece of work.

### Added — the Safari Zone: `quest('surf')`, `quest('strength')` and `safari(...)` battles (#215)
- **Safari battles are playable.** Their menu is BALL / BAIT / GO NEAR / RUN (no moves, party or Bag), so a battle that sets the Safari
  flag gets its own tool list (`safari`, `inspect_pokemon`, `team_report`, `press_button`, `advance_dialog`, `answer_prompt`,
  `close_menus`) and `safari(action, nickname?)`: `ball` (= `catch()`, with the nickname flow, confirmed by the Safari Ball counter),
  `bait`, `rock`, `run`. The observation says what the foe is, whether it is worth a ball and what rock/bait do; the overworld shows
  "SAFARI ZONE: N steps and M Safari Balls left". Counters found by scanning EWRAM (30 balls / 600 steps); the menu's controller
  values (0x080DD739 first turn, 0x080DD57D after) found live — A is only ever pressed AT the menu, once.
- **`quest('surf')` / `quest('strength')`** (registry entries): pay ¥500, walk Center → East → North → West, take the Gold Teeth and the
  Secret House's HM03 on the same visit, walk out ('leaving early?' → YES) and, for Strength, return the teeth to the Warden; the HM
  is taught like Cut. Encounters hand over to the model (`safari(...)`) and the quest resumes; it never routes through its own exit
  (which would re-trigger the ¥500 prompt).
- **Navigation bug found on the way: bridges.** The walkable-tile rule only knew elevation 3, so every bridge deck (elevation 4) was a
  wall and the Safari areas looked disconnected. Decks now count when a ramp (elevation 0) joins them to floor, and A* / the
  region generator refuse a direct floor↔deck step (`tilemap_reader.bridge_tiles`, `deck_step_ok`). `knowledge/map_regions.py` was
  regenerated: Victory Road's floors, Cerulean Cave, the Safari areas and some interiors route correctly now.
- New map names for `go_to`: Safari Zone Entrance, Safari Zone Secret House, Warden's House.
- Tests: `tests/test_bridges.py`, Safari gating and registry tests; live tests drive a full Safari battle (bait, rock, ball with a
  nickname, run), both quests end to end on the real ROM, and a catch.

### Added — `save_game`: a real cartridge save, and readiness says when one is due (#215)
- **`save_game()`** drives Start → Save → YES → YES (overwrite) and CONFIRMS the save by the game's own counter: `gSaveCounter`
  (0x0203AA34, found by diffing EWRAM across two saves — one u32 rose by exactly 1 each time) must rise. The screen text isn't
  readable, so this is the only honest check; a save that didn't happen is reported as such. It is separate from `save_state`'s
  emulator slots and works from the overworld only.
- **Readiness:** `save_game() — you earned 1 badge(s) since the last save` / `never saved` / `25 battles since the last save`. Long-term
  memory keeps `saved_badges` / `saved_battles`; the item never outranks a heal/shop "must".
- Tests: `tests/test_save_readiness.py`; a live test saves twice (counter +1 each), checks the memory record and the in-battle refusal.
- Not done under #215: Safari Zone quests, Game Corner prizes.

### Added — `shop(item, quantity)`: buy a specific item from whoever sells it (#215)
- **Where everything is sold, from the decomp** (`tools/gen_shop_stock.py` → `knowledge/shop_stock.py`): every clerk with a buy menu
  (map, position, stock), prices, item names and readable map names. The Celadon Dept. Store turns out to matter: 2F sells TMs
  (Roar, Hyper Beam, Dig, Brick Break, Secret Power, Attract), 4F stones, 5F vitamins and X-items.
- **`shop(item='TM28')`** (or 'Dig', 'Protein', 'Fire Stone', 'X Attack', 'Super Repel'…, with `quantity`) picks the nearest clerk that
  sells it by route, travels there (shop interiors are valid `go_to` names now), stands on the customer's side of THAT clerk's
  counter — worked out from the map, including talking across a counter — buys, and confirms by the bag / TM-case count rising.
  Too little money, or an item nobody sells, is explained before any walking. `shop()` with no item is unchanged.
- **Stale-menu bug fixed on the way:** `sShopData.itemList` keeps pointing at the previous shop's stock, so a second purchase in the
  same session read the old list as "this clerk's menu is up"; it is cleared before talking to a clerk.
- TM28 Dig is also a free story reward (the Rocket Grunt in Cerulean City); the result and the system prompt say so.
- Tests: `tests/test_shop_stock.py`; a live test flies Vermilion → Celadon (Fly, staged badge/flag) and buys a TM and two Super Repels
  from the two clerks on 2F.
- Not done under #215: Game Corner prizes, cartridge saves, Safari Zone quests.

### Changed — the skills' shared state is declared in one place (#214, part 3)
- `agent/skills/state.py::SkillState` lists every field the skills keep between tool calls (trip and stall bookkeeping, the grind
  session, the benched ace, move-learn baselines, warning-once flags, the Vermilion cans…), each with its owner skill, meaning and
  default. `AgentClient` inherits it. The two per-instance dicts (`_trainer_losses`, `_edge_fail`) use a small `lazy` descriptor.
- The implicit patterns are gone: no more `getattr(self, "_trip", None)` fallbacks or `self.__dict__.setdefault(...)`; a skill reads
  a plain attribute. Class-level declarations scattered through `nav`, `overworld` and `movelearn` moved here.
- Guard tests (`tests/test_skill_state.py`): no `self.__dict__` / getattr-fallback on declared state, and any attribute a skill
  assigns on `self` outside `__init__` must be declared in `SkillState` — a new hidden field fails CI instead of becoming a bug.

### Changed — the observation builder leaves `main.py` (#214, part 2)
- `agent/observation.py` replaces the 370-line `build_observation` that lived inline in `main.py` (1,199 → 819 lines). It is now a
  composition of named sections — header, lead, readiness + bag digest, shortcuts (Escape Rope / Dig / Teleport, Repel), trip,
  battle (moves, boosters, volatiles, catch advice), supplies (bag, PP, Mart, PC), gym, field (tiles, items, direction), exits, and
  loop signals — each returning the lines it contributes, in the order the model has always seen them.
- Every import is at module level (the per-tick path no longer imports anything), and reads that can fail on a half-loaded screen go
  through one `_safe(key, fn, default)` that logs the first failure of each kind.
- Behaviour is unchanged: the old and new builders were run side by side on seven real-ROM states (overworld, mid-battle, forced
  switch, a staged wild battle…) and produced byte-identical text; a permanent live test keeps the sections honest.

### Changed — backend capabilities and tolerated failures (#214, part 1)
- **One capability check instead of twenty.** `agent/skills/base.py::SkillBase._wait_idle()` is the only place that asks whether the
  emulator can wait for the screen to settle (the legacy HTTP client now has a no-op `wait_until_idle`, so it is just a fake in tests
  that lacks it). Reader calls the skills used to guard with `getattr(self.reader, …, fallback)` (`is_surfing`, `is_trapped`,
  `read_disabled_move`, `read_dex_owned`, `read_current_map`, `read_current_box`) are plain calls; the test fakes grew the methods.
- **Tolerated failures are logged.** `log_once(key, …)` (moved from nav into `skills/base.py`) now backs every `except Exception` in the
  skills, the client, `main.py` and the event stream that used to swallow silently and carry on with a default: the first occurrence
  of each is logged with its traceback, later ones stay quiet.
- Loop-detection (`ShortTermMemory.stuck`) edge cases are covered by tests: first record, exactly-four idle steps, back-and-forth
  walking, map and battle resets, position-less actions.
- Still open under #214: extracting the observation builder from `main.py`, and the skills' shared state as an explicit `SkillContext`.

### Changed — tool surface, part 2 (#213): 8 tools become 3, one rule for "which Pokémon?"
- **`pc(action, pokemon?, box_pokemon?, detail?, force?)`** replaces `pc_boxes` / `pc_deposit` / `pc_withdraw` / `pc_swap`
  (`action` = list | deposit | withdraw | swap). Missing arguments are reported before anything touches the emulator.
- **`quest(name?)`** replaces `get_ss_ticket` / `get_cut`. `quest()` lists every story quest with ✔ done / ▶ available / … blocked
  (`knowledge/quests.py`, a registry: the next beat — Silph Scope, Poké Flute, Safari Zone — is an entry plus a driver, not another
  top-level tool). Resume hints now read `quest('ss_ticket')` / `quest('cut')`.
- **`reorder_party(first, second?)`** absorbs `set_lead`: with `second` omitted, `first` becomes the lead.
- **One resolver** (`knowledge/targets.py`, `resolve_mon`): slot number, else exact species / nickname, else a unique partial match.
  Two Pidgeys, or "rat" matching Rattata and Raticate, is reported as ambiguous ("slots 2, 4 — name one by its slot number") instead
  of silently taking the first. Used by switch_pokemon, use_item, give_item, teach_move, use_hm, reorder_party and pc.
- 38 → 33 tools in total (33 → 28 offered on the overworld); every hint, the system prompt, budgets and the scripted policy use the new calls.
- Tests: `tests/test_targets.py`, `tests/test_tool_merge.py`; the live tests drive the new tools on the real ROM.

### Added — held items, battle boosters, Repel strategy (#215)
- **`give_item(item, pokemon)`**: Bag → Items pocket → GIVE → the Pokémon, confirmed by the Pokémon's held item changing; an item
  already held is swapped back into the Bag (the game's own prompt is answered). `PokemonStatus.held_item` is decoded from the Growth
  substructure (party and PC). Item effects are generated from the decomp (`tools/gen_held_items.py` → `knowledge/held_items_data.py`).
- **Who should carry what** (`knowledge/held_items.py`): a type-boost item to the highest-level Pokémon that attacks with that type,
  Leftovers / Shell Bell / Quick Claw to the ace, Exp. Share / Lucky Egg to whoever lags, Light Ball / Thick Club / … to their
  species. The observation shows "Holding: …" and one `give_item(…)` suggestion per unheld item, alongside the bag digest.
  Berries (the separate Berry Pouch) are not handled.
- **X-items in battle**: `use_item('X Attack' | 'X Defend' | 'X Speed' | 'X Special' | 'X Accuracy' | 'Dire Hit' | 'Guard Spec.')`
  works (verified live) and says what it did; a battle observation line lists them and when they are worth a turn (a trainer ace,
  not a wild Pokémon).
- **Repel strategy** (`knowledge/repel.py`): "Repel active: N steps left" and, where every wild Pokémon on the map is at or below the
  lead's level, you hold a Repel, the team is built (≥ 4) and nothing there is wanted, a one-line suggestion to use one.
- Not done (still on the list): Game Corner prizes and TM purchases at the Celadon Dept. Store, Safari Zone quests, cartridge saves.

### Added — Escape Rope, Dig and Teleport (out of battle)
- **`use_hm('Dig')` / `use_hm('Teleport')`** drive the party sub-menu and the "return to …?" prompt, and are confirmed by the map
  changing. Dig = leave a cave/forest/dungeon for its entrance (what an Escape Rope does); Teleport = outdoors only, warps to the
  last Pokémon Center you healed at.
- **Rules come from the decomp** (`tools/gen_escape_maps.py` → `knowledge/escape_maps.py`: `allow_escaping` and outdoor map types), so
  a refusal says why ("Dig only works inside a cave, forest or dungeon…") instead of burning a turn or a rope. `use_item('Escape
  Rope')` is gated the same way and reports where it landed. Note Viridian Forest is both escapable and teleportable (verified live).
- **The model is told**: an "Exit shortcut: use_hm('Dig') or use_item('Escape Rope') (n left)…" / "Shortcut: use_hm('Teleport')…"
  observation line only where it applies with this party and bag, plus a system-prompt rule (they abandon the current trip).
- Tests: `tests/test_escape.py`, and live tests for rope, Dig and Teleport against the real ROM.

### Changed — gym / Elite Four / Champion advice comes from the decomp (#211)
- **No more hand-typed levels.** `knowledge/gym_advice.py` builds each opponent's brief from the generated parties
  (`knowledge/gym_teams.py`, now including the Champion's three starter variants): their Pokémon and levels, the types their attacks
  really are, the types that hit most of the team super effectively (from the type chart) and the moves worth planning around
  (sleep, Toxic, Self-Destruct, Recover…). `GYM_ACE_LEVEL` is derived from the same data.
- **Where the model sees it:** the observation inside a gym ("Leader: Koga: Koffing L37, Muk L39, … | hit them with Ground (4/4)…")
  and `team_report` (next leader, or the whole Elite Four plus Gary once all 8 badges are won).
- Removed the never-read `key_threat` / `counter` strings (they had drifted: Elite Four levels were 2-6 off). Fixed the Celadon
  navigation hint (TM26 is Giovanni's; the Game Corner sells Ice Beam / Thunderbolt / Flamethrower / Shadow Ball / Iron Tail).
- Tests: a navigation-prose check fails if any "Species L<n>" in the hand-written text disagrees with the decomp.

### Fixed — nav driver review (#216)
- **Travel rules are data.** `knowledge/travel_rules.py`: `PC_TOWNS` and `NO_WALK` (the Cerulean → west "Route 4 ledges only go one
  way" rule) moved out of the skill code. The no-walk message now says what to do for *this* party: "Pidgeotto knows Fly: fly_to the
  nearest visited town", "…but you need the Thunder Badge", "Pidgey could learn it — teach it", or "catch a Fly-capable bird".
- **Why a trip ended is recorded.** `_go_to` is a wrapper that records `last_trip_stop = {reason, target, map}` and emits one `trip`
  event per outermost trip: `arrived`, `battle`, `battle_unresolved`, `lost`, `low_hp`, `no_route`, `gated`, `no_walk`, `stall`,
  `blocked`, `budget`, `nested`, `unknown_destination`. A spent hop budget now says so ("…after the 40-hop budget") instead of reading
  like an interrupted trip. The classification of battle stop messages is pinned by a test.
- **Re-entrancy guard.** Travel nested more than 4 deep (go_to → gym city → first-visit heal → go_to(Pokémon Center)…) stops with `nested`
  instead of recursing; the counter always unwinds. The first-visit heal is now announced as a `trip` event.
- **Tolerated failures are logged once** (`_log_once`) instead of `except: pass`: a failing forced-switch while advancing to control,
  and a gate check that couldn't read the game (still treated as met so travel isn't blocked).
- **Warp probing** stops when a wild/trainer battle starts mid-probe, and a battle during a probe is no longer counted as a dead edge.
- **`walk_to` validates its tile** against the map size ("(3,15) is outside this map — valid tiles are x 0-19, y 0-14"); internal
  callers still aim at edge/warp tiles through `_walk_to` directly.

### Removed — the reward tracker; run statistics from the event stream instead (#212)
- **Why.** The shaped→sparse reward was a scoreboard nothing read: never shown to the model, no policy or stop condition used it, the
  Elite Four / Champion terms (#22) could never fire, and several events mis-fired. Decision: delete it rather than keep a number
  that implies steering (option A in the issue). #22 is moot.
- **What replaces it.** `events.run_stats()` / `events.stats_line()` — battles by real outcome (won / lost / fled / caught / drew),
  trainer wins, catches, level-ups, evolutions, faints, blackouts, badges, new towns, key items, heals — printed at the end of a
  run ("steps=120  badges 2 · battles 41 (36 won, 3 fled, 2 caught) · catches 2 · level-ups 17 · …"), carried in
  `EpisodeResult.stats` (the eval scorecard's old `reward` column is now "events", e.g. `3W 1F 2C · 5↑`) and in `run.jsonl`'s `end`
  record. Cumulative counters (`battles_*`, `pokemon_caught`) stay in `progress.json`.
- **Removed.** `agent/reward.py`, `RewardTracker`, `_apply_rewards` (now `_apply_progress`: badges → milestones + LTM, key items,
  the starter), `newly_fainted_slots` (faints come from the event observer, per Pokémon), the journal's per-row `reward` (old journal
  files still load: unknown keys are ignored), `total_reward` in `progress.json` (old files are cleaned on load), the CLAUDE.md reward
  table and `tests/test_reward.py`.

### Changed — the model is only offered the tools that fit the screen (#213)
- **Context-gated tool lists** (`agent.tools.tools_for`, re-read every tool round so a `go_to` that turns into a battle switches
  lists mid-step): a **battle** gets 11 tools (the battle skills, `use_item`, `inspect_pokemon`, `team_report`, and the button /
  dialog / prompt escape hatches) ≈ 1.2k tokens; the **free overworld** drops the battle-only and naming-screen tools ≈ 3.9k tokens;
  **every other context** (menus, dialog, transitions, unknown, or an unreadable screen) is offered everything. Down from ≈ 5.6k tokens
  of schema on every call. The list is stable within a context, so a provider's prompt cache survives a whole fight or walk. In battle
  `use_item` carries a battle-specific description (the field version lists stones / Rare Candy).
- **Descriptions trimmed** for the 22 longest tools (guidance that lives in the system prompt or the situational observation lines was
  repeated in every schema); a test caps any description at 650 characters and the per-context token budgets.
- **CLAUDE.md's tool list is generated** (`tools/gen_tool_docs.py` → a table between markers: tool, where it is offered, arguments, what it
  does) and a test fails if it goes stale — the old hand-written list was missing ~25 shipped tools (part of #211).
- Consistency test: every schema has a dispatcher case. Unchanged on purpose (still on #213): merging `set_lead` / `reorder_party` and the
  `pc_*` tools into one each, a `quest(name)` registry replacing `get_ss_ticket` / `get_cut`, and one shared party/box target resolver —
  they rename tools the prompt, the scripted policy and the logs all mention, so they deserve their own PR once gating has been watched.

### Removed — dead code from the pre-Nov-13 audit (#214)
- **Deleted, no remaining use:** `tools/diagnostic.py` and `tools/diagnostic_tilemap.py` (≈650 lines, HTTP-backend-only, built on
  addresses the code no longer trusts); dead methods in the move-learn, PC, overworld and quest skills (`_accept_forget_slot0`,
  `_storage_base`, `_party_full_hp`, `VERMILION_GYM`); `read_bag_count`, `read_box_mon` (public single-slot reader; `read_boxes` /
  `_decode_box_mon` remain), both `tap_many`s, `active_party_member`, `type_chart.best_move_type`, `reconcile_badges_from_ram` (the
  monotonic reconciler nothing called — only `reconcile_badges_authoritative` at startup), `STARTER_RECOMMENDATION/REASON`, the
  autopilot nickname generator (`auto_name`, its pun/pool tables, `GUIDANCE`), unused `Addr` constants (`BADGES`, `OVERWORLD_FLAG`,
  `BATTLE_FLAGS`, `PARTY_MENU_SLOT`, `FLAG_SYS_USE_STRENGTH`), unused config (`DECISION_INTERVAL`, `HP_HEAL_THRESHOLD`, the
  `LM_STUDIO_BASE` alias — the env var is still honoured as a fallback for `LLM_BASE_URL`), `_RunState.battle_start_lead` /
  `battle_active_slot` (superseded by the event-stream battle tracker) and `ShortTermMemory`'s never-read `current_state`,
  `last_state`, `last_diff`, `battle_turn`, `consecutive_same_action`.
- **Tidied:** LTM's corrupt-file warning uses the logger instead of `print`; tests for deleted code removed or pointed at the
  surviving API; more `ShortTermMemory` loop-detection tests (history cap, new-map and new-battle resets, moving while repeating).
- **Guard:** `tests/test_dead_code.py` fails CI when a function / method / class in `agent game knowledge memory evals` is referenced
  nowhere else (tests don't count; generated tables exempt; a short allow-list for deliberate APIs). 
- Not done here (still on #214): the `hasattr(self.mgba, "wait_until_idle")` capability checks (~20 sites; needs the test fakes
  updated), the narrow-exception pass, extracting the observation builder from `main.py`, and replacing the AgentClient mixins'
  hidden shared state with an explicit context.

### Added — IV / EV / nature awareness and a per-Pokémon quality score (#208)
- **Decoded.** `PokemonStatus` and the boxed-Pokémon dicts now carry IVs, EVs, friendship, ability slot and the game's own
  computed stats (IVs/EVs from the already-decrypted E / M substructures; layout per the decomp). Pokémon are identified by
  personality value, nature = PID % 25. `tools/gen_base_stats.py` → `knowledge/base_stats.py` (base stats + EV yields).
- **`knowledge/mon_quality.py`** (pure): the Gen III stat formula, Hidden Power (type and power from the IVs), and `assess` — a
  score in [0, 1] = 0.8 × role-weighted IV share + 0.2 × nature fit, graded excellent / good / average / below average. The role
  (physical / special / mixed) comes from base stats and the damaging moves known, so a special attacker's Attack IV and an
  Attack-lowering nature are not held against it. **Golden-checked live:** base stats + decoded IVs / EVs / nature + the formula
  reproduce the stored stats of every party Pokémon exactly.
- **Where it shows up.** The catch result reports the new Pokémon's `Quality:` (found by personality value, in the party or the PC)
  with a comparison to the same species you already have or to the team average — *after* the catch, like a human would see it;
  new `inspect_pokemon` tool (stats, IVs, EVs, nature, Hidden Power, grade, team comparison); `pc_boxes(detail=true)` grades boxed
  Pokémon; a readiness item "better specimen in the PC — pc_swap('Pidgey', '1:4')" appears in Pokémon Centers when a boxed
  specimen of a species you field beats yours by 12+ points (levels lost are mentioned); the `catch` event line shows the grade.
- **Hidden Power** is finally real in battle: the ranker scores it with its true type and power, the move list shows
  "Hidden Power is Water 56 for this Pokémon (from its IVs)" (closes the loose end from #204).
- **Opt-in pre-catch peek:** `IV_PEEK_BEFORE_CATCH=true` adds a "Foe IVs (peek enabled)" line for wild Pokémon. Default off — a human
  has no IV readout in Gen III — and runs with it on are not comparable to runs without.
- Not done: EV training plans (which route/foe trains the wanted EV), vitamins as EV tools, replacing a party member by a *different*
  species on quality alone (catch_policy still decides by line strength).

### Added — team composition awareness (#207)
- **`knowledge/team.py`** (pure): coverage from the moves a team actually knows, shared weaknesses (≥ 3 members), who can carry
  each HM (Cut / Fly / Surf / Strength) against the badge count at which the story needs it, and a **fit check against the next
  Gym Leader's real party** (`tools/gen_gym_teams.py` → `knowledge/gym_teams.py`, first-battle parties of the 8 leaders + the Elite
  Four from the decomp): "hits 0/3 of Lt. Surge's Pokémon super effectively, 1/2 members safe from his types".
- **Hunt hints with real locations.** When the team doesn't answer the next gym (or no one can learn an HM it is about to need) the
  readiness block says what to catch and where: `Diglett — Diglett's Cave B1F (grass L15-22); Sandshrew — Route 4 (grass L6-12)`,
  taken from the LeafGreen wild-encounter tables (`tools/gen_wild_locations.py`, Kanto only — the old hand-written counter text
  could not be wrong about a version difference like Oddish/Bellsprout because it is no longer from memory). If a counter is already in the
  PC the hint is `pc_swap` it in. The curated per-gym shortlist is validated against the tables by the tests.
- **Catch policy.** `evaluate(..., wanted=…)`: a species that fills a gap is worth a ball whatever its BST (within the premium level
  debt; a full party sends it to the PC with a `pc_swap` hint). Used by the battle observation, `go_to`/`grind` encounter briefs and
  the grind autopilot gate.
- **`team_report` tool** (read-only): the full report above on demand.
- Not done: an "availability curve" for how good a species is at a given point of the story (the BST-based line value still stands in);
  Elite Four fit checks (the data is generated, the hints cover the 8 gyms).

### Added — the model knows what is in its Bag (#205)
- **TM upgrades.** `knowledge/bag.py::tm_advice` scores each owned TM against every compatible party member with the battle
  ranker's expected-damage function (`move_score`: STAB, accuracy, a +15% bonus for a new damaging type) and only flags clear
  upgrades (≥ 55 and ≥ 1.3× the move it replaces via `pick_forget`; a free slot needs a new type or ≥ 1.2× the best attack).
  They appear as `TM upgrade — teach_move('TM13', pokemon='Lapras', forget='Growl') — Ice Beam (~164) replaces Growl` readiness
  items (a "should", never over a heal). HMs are never advised as upgrades.
- **Bag digest.** A `BAG — TMs: … | HMs: HM01 Cut (known by Ivysaur), HM03 Surf (NOT taught yet) | Items: Thunder Stone, Rare
  Candy×2` line shows when the contents change and every 30 ticks, plus `Fire Stone: Growlithe can evolve (→ Arcanine)` notes
  (`tools/gen_evolutions.py` → `knowledge/evolutions.py`, item-triggered evolutions from the decomp).
- **`teach_move` preview.** A single-use TM that would make a Pokémon with four moves forget one first returns the plan
  ("Would teach Ice Beam to Lapras, forgetting Growl … confirm with teach_move(…, forget='Growl')"); naming `forget` or
  `confirm=true` commits. HMs and free slots are unchanged.
- **`use_item` for stones, Rare Candy and vitamins.** Evolution stones pick the Pokémon that can use them (or ask when several
  can) and the evolution scene is played with A (B would cancel it); Rare Candy / HP Up / Protein / Iron / Carbos / Calcium /
  Zinc require a named `target` and report the level change. Verified live through the real Bag → party screen flow.
- Not done: `give_item` / held items and berries, X-items in battle, buying TMs (Game Corner / Celadon) — tracked on #215.

### Fixed — battle outcome and progress accounting (#210)
- **Real outcomes.** Battles are booked from `gBattleOutcome` (via the event stream's end-of-battle hook, which fires exactly
  once per battle wherever it was fought — including the hundreds inside `grind()` that the old main-loop edge detector never
  saw). `battles_won` counts only wins; new `battles_fled`, `battles_caught` counters; losses and `total_battles` are exact.
  Added the missing `B_OUTCOME_*` constants (ran / teleported / foe fled / foe teleported).
- **The journal has data.** Rows now carry the foe and its level, the turns and distinct moves actually used, the Pokémon that
  fought, its HP at the end and notes (`trainer Geodude, lost, whole party fainted`); outcomes are `win` / `loss` / `fled` /
  `caught` / `draw`. `get_loss_lessons` finally has turns and moves to show instead of "Turn 0 … unknown".
- **Catches.** `pokemon_caught` counts real catches (the starter and PC withdrawals no longer inflate it); `caught_new` fires
  only when the Pokédex gains an entry.
- **Identity, not slot index.** `StateDiff` (level-ups, HP, new moves) and `newly_fainted_slots` pair Pokémon by personality value, so
  `set_lead`, switches and party-screen reorders no longer read as a faint + a miss or two level-ups, and an evolution is the
  same Pokémon. A genuinely new party member stays unpaired.
- LTM saves are debounced (≤ once per 5 s, immediately on a loss or catch) now that fights inside skills are booked too.

### Added — a live game-event stream in the terminal (#209)
- `agent/events.py`: one compact line per event (and an `ev` record in `run.jsonl`): every **tool call** with its arguments,
  a one-line result and timing (was: name + 80 chars); **battle start / end** classified from `gBattleOutcome`
  (won / lost / fled / caught / drew…) with foe, level and place; **level-ups, evolutions, faints, new moves, party
  joins/leaves, badges** (gym leader named); **catches** (species + nickname, "→ PC box" when the party was full);
  **heals, shop purchases, PC deposits/withdrawals, HM use / Fly, trip legs** (arrived / encounter handed to the model),
  key items, new towns, milestones, blackouts, checkpoints, the model's reasoning line, and a periodic `STATUS` line
  (badges, party HP, ¥, balls, LLM calls/tokens, wall minutes).
- Events come from where they happen: explicit emits in the skills, plus `events.observe(reader)` — a cheap snapshot diff
  run after every tool, every battle move and every main-loop tick — so the hundreds of fights inside one `grind()` /
  `go_to()` / `heal()` call are no longer invisible. Pokémon are tracked by personality value, so reordering the party
  isn't an event and evolutions/level-ups attach to the right mon.
- `LOG_LEVEL=quiet|events|debug` (default `events`) and `STATUS_EVERY` (default 25 ticks) in `.env`; the `OBS:` dump moved to
  `debug`. Not done here: the journal / reward / `battles_won` accounting still uses the old win/loss rule (#210).

### Fixed — PC driver (#206)
- **Full-box deposits.** The game's "Deposit in which BOX?" chooser always starts on Box 1 (the decomp resets
  `sDepositBoxId` each time the storage screen opens) and refuses a full box instead of moving on, so a 30/30 Box 1 made
  every `pc_deposit` fail with a vague retry message. The deposit now picks the first box with room from the stored
  counts and steers the chooser there with Left/Right (`pick_deposit_box`); "all 14 boxes are full" is reported plainly.
- **No more guessing.** `pc_swap` resolves both sides and vets the deposit before touching anything, and withdraws the
  boxed Pokémon by its exact `box:slot` (a name could match the Pokémon that was just deposited). A name matching several
  boxed Pokémon returns the list ("2 Pokémon match 'pidgey': 2:11 Pidgey (L14), 1:4 Pidgey (L8) — use box:slot")
  instead of grabbing the highest level. If the withdrawal fails after the deposit it says the party is one short.
- **HM guard.** `pc_deposit` / `pc_swap` refuse to store the only Pokémon that knows an HM move unless `force=true`.
- **The model can see the boxes.** `pc_boxes` is compact by default (per box count, names, levels);
  `pc_boxes(detail=true)` adds box:slot, types, moves and which HMs each could learn. A Pokémon Center observation line
  says how many Pokémon are stored. `read_boxes` reads one memory block per box (14 reads instead of 420).
- PC screen addresses moved into `game.constants.Addr` (`STORAGE_CB2`, `STORAGE_CURSOR_AREA/POS`, `MB_PC`).

### Changed — moves are ranked by what they actually do (#204)
- `tools/gen_move_effects.py` → `knowledge/move_effects.py`: every move's decomp `effect`, accuracy, priority, secondary
  chance and target. `knowledge/move_semantics.py` turns that into `move_score` (expected damage per turn), `role_tag`
  (what a move is for / when it fails) and `catch_setup_hint`.
- `move_score` = power × accuracy × STAB × type effectiveness, except: Dream Eater needs a sleeping foe; one-hit KOs,
  Counter / Mirror Coat / Bide, Focus Punch, Snore and Explosion are never auto-picked; Solar Beam / Fly / Dig and Hyper
  Beam count half; Return / Frustration use friendship (≈28 / ≈74 for a fresh catch, not 102); Seismic Toss / Night
  Shade / Dragon Rage / Sonic Boom / Super Fang use their real fixed damage (no STAB, no super-effective bonus, type
  immunity respected); Flail / Eruption use your HP; Hidden Power ignores type guesses (its type comes from IVs).
- Used by the auto-fighters (`_best_damaging_move(..., ctx)` with `_battle_ctx()`), the "Best move" line and the idle
  nudge. `SUICIDE_MOVES` is now derived from the effect table.
- "Your moves" now carries a tag per move (Mean Look "traps the foe — use it BEFORE weakening a wild Pokémon", Roar /
  Whirlwind "ENDS a wild battle", Protect "fails if used twice in a row", Splash "does nothing", Disable, Wrap, sleep /
  paralysis "FAILS if the foe has a status condition", accuracy under 85%…). Wild battles with balls and a worthwhile
  species also get a "Catch setup you have: False Swipe …" line (replaces the removed auto-weakening).
- Not done: refusing certain-fail moves in `use_move`, using Hidden Power's real type (needs IVs, #208), a planner for
  status-move plans (Substitute / Rest / setup).

### Changed — grind() rework: fixed floor, benched ace, level-fit routes, model-driven fights (#203)
- **Encounters are handed to the model.** `grind` paces on grass until a wild Pokémon (or trainer) appears, then the call
  ends with a brief (foe, catch verdict, who should fight, progress); the model plays it with `use_move` / `use_item` /
  `catch` and calls `grind` again. The session (`AgentClient._grind_run`: floor, starting levels, battle count) persists
  between calls. `auto_battles=N` autopilots the next N *boring* wild fights (foe ≤ active level + 2, nothing worth a
  ball); a forced-replacement screen after a faint is handed over too (`switch_pokemon`). The `catch` flag now only
  controls whether worthwhile wild Pokémon are pointed out — grind no longer throws balls or names catches itself.
- **Fixed floor, not a moving target.** Balance mode trains everyone up to `top − 7` *measured when the session starts*,
  capped at the next gym's recommended level (`knowledge.party.grind_floor`); the ace's gains no longer move the goal.
- **The ace is benched.** `pick_finisher(..., bench=(ace,))` never picks the strongest mon as finisher unless nobody
  else is fit (counted as `ace_fought`); the brief tells the model not to switch to it.
- **Stop-loss.** After 20+ battles, if the ace gained 3+ levels while the lowest member gained ≤1, grind stops with a
  diagnosis (`ace_runaway`). Sessions are also capped at 150 encounters.
- **Routes chosen by wild level.** `tools/gen_encounters.py` → `knowledge/encounters.py` (LeafGreen land-encounter
  min/avg/max level per map); `knowledge/grind_routes.best_grass` picks the reachable grass whose levels fit the
  Pokémon being trained, and grind relocates when the trainee outgrows (or is outclassed by) the current route.
- **Quests no longer autopilot (follow-up).** `get_ss_ticket` / `get_cut` travel in `yield` mode: a wild Pokémon or trainer
  ends the call with the usual brief, but the resume call is the quest tool itself (`get_ss_ticket()`; stored in
  `_trip["call"]`, shown in the `TRIP IN PROGRESS` line). New `auto_trainers=true` on both fights the Nugget Bridge / ship
  trainers for you. The `autopilot` travel mode and everything behind it are gone: `_is_new_team_species`,
  `_travel_wants_xp`, the in-trip auto-catch/auto-XP fights, `_grind_try_catch`, `_travel_fights/_travel_caught`.
  Short scripted walks inside quests (`_press_on_tile`: Clefairy, Bill's computer, the Captain, Vermilion's trash cans)
  still clear an incidental battle as plain transport (`flee` mode) and hand back to the model what they cannot.
  `_solve_vermilion_switches` remembers the two can ids across an interruption and presses a can from either side if the
  tile below is taken.
- Relocation trips use `go_to`'s `flee` mode; `_restore_ace_lead` / `_grind_finish` never auto-play a battle; a stale
  session is dropped when the model goes off to travel/heal/shop (`_grind_abandon`). `_no_attack_turn` unchanged.

### Changed — go_to hands encounters to the model (#202)
- `go_to` no longer plays wild battles itself. When a wild Pokémon appears (or a trainer spots you) the call ends with
  a description (species, level, HP, catch-policy verdict, balls) and the exact resume call; the model fights /
  catches / switches / flees, then calls `go_to` again — with no destination it resumes the trip in progress
  (`AgentClient._trip`, shown in the observation as `TRIP IN PROGRESS`). `auto_trainers=true` keeps the old
  auto-fight for trainers on long marches.
- Travel modes (`NavMixin.TRAVEL_MODES`): `yield` (go_to, shop, pc_*), `flee` (heal() and the grind restock trip: wild
  battles are fled, no low-HP stop), `autopilot` (legacy catch/XP/flee heuristic, kept for grind's route relocation
  and the Bill / S.S. Anne quests until #203 reworks them).
- Known: battles triggered inside `walk_to`'s puzzle solver still use autopilot. Live tests `get_ss_ticket` /
  `get_cut` fail on main as well (not caused by this change).

### Fixed — Self-Destruct/Explosion training loop (run 20261114-145026)
- `_best_damaging_move` ranked by raw power, so a Geodude with Self-Destruct (200) always picked it: the trainee
  fainted every fight, gained no XP, was revived, and grind looped for hours (4 × 100-min time limits).
  `SUICIDE_MOVES` (Self-Destruct, Explosion) are now skipped by the auto-fighters and the "Best move" hint;
  with only a suicide move left the caller gets `None` → switch/flee (`_no_attack_turn`).
- `use_move` refuses them while any other damaging move has PP; the battle observation and system prompt say why.

### Fixed — training swap-back, false "balanced", party composition (watched-run follow-up)
- fix(training): `_train_fight` swapped the trainee back in right after tagging it out for the ace (its `switched_in`
  flag was only set when it had been brought in, not when it started the battle) — so the trainee took the foe's hits
  for no XP. Rewritten as a proper tag-switch: trainee starts → (easy foe: fights alone) / (otherwise: switched out on
  TURN ONE for a finisher) → never swapped back. The finisher is the lowest-level *capable* teammate
  (`knowledge.party.pick_finisher`), so finishing XP rotates through the whole team instead of always feeding the ace.
  A benched trainee (travel fights) is brought in only if the free hit is survivable. Verified live: a L3 trainee
  gains XP, keeps its HP, one switch per battle.
- fix(grind): a fainted trainee dropped out of `lagging_mons`, so "Party balanced" was reported beside L7/L6/L5 mons
  and an L38 ace (they were just fainted). Fainted members now count as lagging.
- change(balance): the rule is now "nobody more than 7 levels under the top" (was ratio 0.75 → 10 levels at L40).
- change(grind): `grind(level=N)` raises the BEST Pokémon to N (not the lead) and still rotates lagging teammates in;
  restock uses the whole-team check instead of the lead's HP/PP. Travel trainer battles also rotate a lagging mon in.
- feat(catch): `go_to` no longer flees worthwhile wild Pokémon — it weakens and catches them (autopilot nickname) when the
  catch policy says so, and reports "Caught on the way". The old "offer once, only when the team is under 4" path never
  built a team past four. Policy: bigger debt allowances (8 / 16), a *stronger line than the team's weakest member* is an
  upgrade (also with a full party — it goes to the box with a `pc_swap` hint), weak lines that only add a type stay strict.
- feat(prompt/obs): battle observation gets an `XP SHARE` line (lead with the weak mon, switch on turn 1), and the
  prompt gains party-composition and tag-switch guidance.

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
