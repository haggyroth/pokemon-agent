from datetime import datetime
from config import MGBA_BACKEND, START_FROM_SAVE, START_FROM_STATE, MAX_STEPS, USE_VISION
from game.memory_reader import LeafGreenReader
from game.state import GameContext, active_party_member, newly_fainted_slots
from game.tilemap_reader import TilemapReader
from agent.lm_studio_client import AgentClient
from agent.reward import RewardTracker
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.battle_journal import BattleJournal, BattleRecord
from knowledge.system_prompt import build_system_prompt
from knowledge.navigation import get_travel_direction, DIRECTION_BUTTON, MAP_NAMES, infer_building_type
from knowledge.leafgreen_data import BADGE_BIT_MILESTONE, GYMS, POKEMON_TYPES
from game.constants import Addr
from knowledge.battle import battle_summary
from rich.console import Console
import time, sys

console = Console()


def _frame_chroma(mgba) -> float:
    """Mean chroma (max−min channel) over a coarse grid of the framebuffer.

    The FRLG quest-log recap renders the whole screen in a heavily *desaturated*
    palette (chroma ≈ 8–15), while normal gameplay is full color (chroma ≈ 60+).
    That gap is what lets us tell the recap apart from real play. Native backend
    only; returns a high value if no framebuffer is available so callers treat it
    as "not a recap".
    """
    fb_fn = getattr(mgba, "framebuffer", None)
    if fb_fn is None:
        return 999.0
    fb = fb_fn()
    W, H = 240, 160
    total = count = 0
    for y in range(0, H, 9):
        for x in range(0, W, 9):
            i = (y * W + x) * 4
            total += max(fb[i], fb[i + 1], fb[i + 2]) - min(fb[i], fb[i + 1], fb[i + 2])
            count += 1
    return total / count


# Above this mean chroma the screen is full-color gameplay; below it we're still
# in the desaturated quest-log recap. The two regimes are ~8 vs ~60, so the exact
# cutoff is not sensitive.
_RECAP_CHROMA_CUTOFF = 40.0


def drive_into_gameplay(mgba, reader) -> bool:
    """Boot from the loaded battery save through the pre-gameplay gates into real
    player control. Returns True once normal gameplay is reached.

    Two gates, each with its own tell:

      1. **Title screen / Continue menu** — not in the game world yet (map bank
         reads 0). Press A until a map loads (this taps through "PRESS START" and
         selects Continue).
      2. **Quest recap** ("Previously on your quest…") — the trap. It auto-plays a
         desaturated replay of recent events and *masquerades as OVERWORLD*
         (field callback, no fade, no menu), so detect_context() and position
         both lie: the recap even auto-animates the player. Neither A-mashing nor
         waiting escapes it — **B skips it**, and the palette snaps back to full
         color when it clears. So we press B until the frame is no longer
         desaturated (see _frame_chroma).
    """
    mgba.reset()
    mgba.run_frames(200)                      # boot logos

    for _ in range(80):                       # gate 1: title + Continue → game world
        if mgba.read8(Addr.MAP_BANK) != 0:
            break
        mgba.tap("A")

    for _ in range(80):                       # gate 2: skip the recap with B
        if _frame_chroma(mgba) > _RECAP_CHROMA_CUTOFF:
            mgba.tick(10)                     # let the last transition settle
            return True                       # full color → normal gameplay
        mgba.tap("B")
    return False                              # budget exhausted; hand off anyway


def main():
    console.rule("[bold green]Pokemon LeafGreen LLM Agent")
    if MGBA_BACKEND == "native":
        from game.mgba_core import NativeMGBAClient
        mgba = NativeMGBAClient()
    else:
        from game.mgba_client import MGBAClient
        mgba = MGBAClient()
    if not mgba.verify_connection():
        console.print(f"[red]ERROR: emulator not ready or wrong ROM (backend={MGBA_BACKEND}).")
        console.print("Expected AGB-BPGE (Pokemon LeafGreen). Check ROM_PATH / startup order.")
        sys.exit(1)
    console.print(f"[green]Connected ({MGBA_BACKEND}): {mgba.get_game_title()} ({mgba.get_game_code()})")

    reader  = LeafGreenReader(mgba, decrypt=True)

    # Optionally load an mGBA save STATE directly — instant, no title/Continue/
    # recap. Takes precedence over START_FROM_SAVE (native only).
    if START_FROM_STATE and MGBA_BACKEND == "native":
        if mgba.load_state_file(START_FROM_STATE):
            mgba.tick(30)   # let post-load fade/flags settle before first read
            s = reader.read_state()
            console.print(f"[green]Loaded save state: {START_FROM_STATE} "
                          f"(map {s.map_bank}/{s.map_id}, pos ({s.player_x},{s.player_y}))[/]")
        else:
            console.print(f"[red]Could not load save state: {START_FROM_STATE}[/]")
    # Otherwise, optionally boot from a battery save and drive to "Continue" so the
    # agent starts in real gameplay instead of the new-game intro (native only).
    elif START_FROM_SAVE and MGBA_BACKEND == "native":
        if mgba.load_save(START_FROM_SAVE):
            got_control = drive_into_gameplay(mgba, reader)
            where = f"map {mgba.read8(Addr.MAP_BANK)}/{mgba.read8(Addr.MAP_ID)}"
            if got_control:
                console.print(f"[green]Continued from save: {START_FROM_SAVE} ({where})[/]")
            else:
                console.print(f"[yellow]Continued from save but could not confirm player "
                              f"control ({where}) — may still be in the quest recap[/]")
        else:
            console.print(f"[red]Could not load save: {START_FROM_SAVE}[/]")

    tilemap = TilemapReader(mgba)
    ltm     = LongTermMemory()
    client  = AgentClient(mgba, reader, ltm)
    stm     = ShortTermMemory()
    journal = BattleJournal()
    reward  = RewardTracker(shaped=True)

    ltm.new_session()
    console.print(f"Session #{ltm.data['session_count']} | Badges: {ltm.data['badges_earned']}/8 | "
                  f"Milestones: {len(ltm.data['milestones'])}")

    # ── Startup badge reconciliation ─────────────────────────────────────────
    # Game RAM is the source of truth for badges — it IS the actual save state.
    # We never write it. Instead we fold any badges RAM shows into LTM, which is
    # a monotonic record for reward/milestone tracking. RAM can legitimately
    # regress when the agent load_state()s to retry a gym, so we must not un-earn
    # milestones or (worse) fabricate badges by writing LTM's belief back to RAM.
    _adopted = ltm.reconcile_badges_from_ram(mgba.read8(Addr.BADGES))
    if _adopted:
        console.print(f"[yellow]Adopted badges from game save into LTM: {', '.join(_adopted)}[/]")
    del _adopted

    prev_state           = None
    battle_was_active    = False
    battle_start_lead    = ""   # species name of our lead when battle began
    current_enemy        = ""   # last known opponent species name (set by LLM via tool or detected)
    battle_active_slot   = 0    # party slot of the Pokémon actually fighting (see below)
    battle_is_trainer    = False  # whether the current battle is vs a trainer (gBattleTypeFlags)
    prev_key_items       = None   # count of bag key items (reward key_item on increase)
    prev_map_key         = None
    transitioning_steps  = 0
    pending_map_b64      = None   # area map to attach next tick (cleared after one use)
    pending_map_name     = ""
    step_count           = 0

    while True:
        try:
            state = reader.read_state()
            diff  = reader.diff(prev_state, state)
            stm.current_state = state
            stm.last_state    = prev_state
            stm.last_diff     = diff

            in_battle = state.context == GameContext.IN_BATTLE
            if in_battle and not battle_was_active:
                stm.reset_for_new_battle()
                ltm.data["total_battles"] += 1
                battle_start_lead = state.party[0].species_name if state.party else ""
                battle_active_slot = 0
                # Classify the battle from gBattleTypeFlags (set at battle init).
                battle_is_trainer = bool(mgba.read32(Addr.BATTLE_TYPE_FLAGS)
                                         & Addr.BATTLE_TYPE_TRAINER)
                current_enemy = ""
                client._current_opponent = ""

            # Track which of our Pokémon is actually fighting. In single battles
            # only the active mon's HP changes, so the last slot to take damage
            # is the one that's out — remembered so battle-end logging records the
            # fighting mon, not always the lead (#2).
            if in_battle and diff.hp_changed:
                battle_active_slot = diff.hp_changed[-1]

            # ── Battle end detection ────────────────────────────────────────
            if battle_was_active and not in_battle:
                active_mon = active_party_member(state.party, battle_active_slot)
                lead_hp_pct = active_mon.hp_percent if active_mon else 0.0
                active_species = active_mon.species_name if active_mon else battle_start_lead
                all_fainted = bool(state.party) and all(p.current_hp == 0 for p in state.party)
                outcome = "loss" if all_fainted else "win"
                # Pass enemy name for journal + system prompt loss-lessons
                current_enemy_snap = current_enemy
                current_enemy = ""
                if outcome == "win":
                    ltm.data["battles_won"] += 1
                    # Reward trainer wins (wild wins aren't in the schedule). Gym
                    # leaders are trainers too and additionally fire gym_leader_win
                    # on the subsequent badge — a negligible +1 overlap.
                    if battle_is_trainer:
                        reward.reward("trainer_win")
                else:
                    ltm.data["battles_lost"] += 1
                location = MAP_NAMES.get((state.map_bank, state.map_id),
                                         f"bank={state.map_bank},id={state.map_id}")
                journal.log(BattleRecord(
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    location=location,
                    enemy_name=current_enemy_snap or "unknown",
                    enemy_level=0,
                    player_lead=active_species,
                    outcome=outcome,
                    turns=0,
                    moves_used=[],
                    hp_remaining_pct=round(lead_hp_pct, 2),
                    reward=0.0,
                    notes="",
                ))
                console.print(f"[magenta]Battle {outcome}[/] | active={active_species} hp={lead_hp_pct:.0%}")
                ltm.save()
            # Save the pre-update value so the auto-tap guard below can see
            # whether we were in battle on the PREVIOUS tick (battle_was_active
            # is about to be overwritten with the current tick's value).
            was_in_battle_prev_tick = battle_was_active
            battle_was_active = in_battle

            # Auto-advance a stuck dialog / transition with A. Fires for
            # DIALOG_OPEN (where NPC/sign/item dialogs live) and TRANSITIONING
            # (post-warp/fade message boxes). Not IN_MENU — pressing A there would
            # select a menu item.
            # Guards:
            #   • not in_battle            — don't tap during a battle turn
            #   • not was_in_battle_prev_tick — don't tap on the first tick after
            #                                  leaving IN_BATTLE; context can read
            #                                  TRANSITIONING during post-battle
            #                                  animations and turn-change fades
            if (state.context in (GameContext.DIALOG_OPEN, GameContext.TRANSITIONING)
                    and not in_battle
                    and not was_in_battle_prev_tick):
                transitioning_steps += 1
                if transitioning_steps >= 5:
                    mgba.tap("A")
                    console.print("[dim]transition: tap A[/]")
                    mgba.tick()
                    continue
            else:
                transitioning_steps = 0

            # Refresh tilemap cache whenever the map changes
            map_key = (state.map_bank, state.map_id)
            if map_key != prev_map_key:
                tilemap.refresh()
                stm.reset_for_new_map()
                # Town-visit tracking
                town_name = MAP_NAMES.get(map_key)
                if town_name and state.map_bank == 3 and state.map_id < 19:
                    if ltm.add_town(town_name):
                        reward.reward("new_town")
                        console.print(f"[cyan]New town: {town_name}[/]")
                # Load overhead reference map (attach to next decision step)
                if USE_VISION:
                    pending_map_b64, pending_map_name = AgentClient.load_area_map(*map_key)
                    if pending_map_b64:
                        console.print(f"[blue]Area map loaded: {pending_map_name}[/]")
                prev_map_key = map_key

            # ── Auto-reward + auto-milestone from state diff ────────────────
            if diff.badges_changed:
                # Only reward/record when badge count genuinely increased.
                # A spurious read (e.g. badge_bits glitches 0→non-0→0) would
                # trigger badges_changed without state.badges > prev_state.badges.
                if prev_state is not None and state.badges > prev_state.badges:
                    reward.reward("new_badge")
                    # A badge increase means a gym leader was just defeated.
                    reward.reward("gym_leader_win")
                    # Use raw bitmask diff — state.badges is a popcount (0-8), not
                    # a bitmask, so "state.badges & ~prev_state.badges" was WRONG.
                    newly_set = state.badge_bits & (~prev_state.badge_bits & 0xFF)
                    for bit in range(8):
                        if newly_set & (1 << bit):
                            ms = BADGE_BIT_MILESTONE.get(bit)
                            if ms:
                                ltm.add_milestone(ms)
                                console.print(f"[green bold]Milestone: {ms}[/]")
                            gym = next((g for g in GYMS if g["badge_bit"] == bit), None)
                            if gym:
                                ltm.add_badge(gym["leader"])
                    if reward.shaped and state.badges >= 4:
                        reward.anneal_to_sparse()

            for _ in diff.level_changed:
                reward.reward("level_up")

            # Penalise each of our Pokémon fainting (once per faint).
            if prev_state is not None:
                for _slot in newly_fainted_slots(prev_state.party, state.party):
                    reward.reward("party_faint")

            # Reward obtaining a key item (bag key-items pocket count increased).
            key_items = reader.read_key_item_count()
            if prev_key_items is not None and key_items > prev_key_items:
                reward.reward("key_item")
                console.print(f"[cyan]Key item obtained (bag key items: {key_items})[/]")
            prev_key_items = key_items

            if prev_state is not None and state.party_count > prev_state.party_count:
                reward.reward("caught_new")
                ltm.data["pokemon_caught"] = ltm.data.get("pokemon_caught", 0) + 1
                # first-party addition → starter chosen
                if prev_state.party_count == 0 and state.party_count == 1:
                    starter = state.party[0].species_name or "Unknown"
                    if ltm.data.get("starter") is None:
                        ltm.data["starter"] = starter
                    if ltm.add_milestone("starter_chosen", f"chose {starter}"):
                        console.print(f"[green bold]Milestone: starter_chosen ({starter})[/]")

            # Persist reward total every tick (cheap)
            ltm.data["total_reward"] = round(reward.total, 2)

            # ── Build observation string ─────────────────────────────────────
            # Use LTM badge count for display — it is the authoritative source
            # (game RAM can hold stale badge data from old saves/sessions).
            obs_parts = [f"Context: {state.context.name}",
                         f"Badges: {ltm.data['badges_earned']}/8"]
            if prev_state is not None:
                dx = state.player_x - prev_state.player_x
                dy = state.player_y - prev_state.player_y
                if dx == 0 and dy == 0:
                    obs_parts.append("Movement: none (position unchanged since last step)")
                else:
                    obs_parts.append(f"Movement: moved ({dx:+d},{dy:+d})")
            if state.party:
                lead = state.party[0]
                obs_parts.append(
                    f"Lead: {lead.species_name or '?'} L{lead.level} "
                    f"HP={lead.current_hp}/{lead.max_hp} ({lead.status})"
                )
                if in_battle:
                    move_names = [m for m in lead.move_names if m]
                    lead_types = POKEMON_TYPES.get((lead.species_name or "").upper().strip(), ())
                    bsummary = battle_summary(move_names, current_enemy,
                                              lead.hp_percent, lead.pp,
                                              attacker_types=lead_types)
                    obs_parts.append(bsummary)
            obs_parts.append(f"Pos: ({state.player_x},{state.player_y}) Map: {state.map_bank}/{state.map_id}")
            if state.context == GameContext.OVERWORLD and tilemap.ready:
                surr = tilemap.surroundings_str(state.player_x, state.player_y)
                obs_parts.append(f"Tiles: {surr}")
                travel_dir = get_travel_direction(state)
                if travel_dir:
                    passable = tilemap.passable_directions(state.player_x, state.player_y)
                    btn = DIRECTION_BUTTON[travel_dir]
                    if passable.get(travel_dir):
                        obs_parts.append(f"Suggested: press {btn} ({travel_dir} tile is floor, matches travel direction)")
                    else:
                        alts = [f"{DIRECTION_BUTTON[d]}({d})" for d, ok in passable.items() if ok]
                        obs_parts.append(f"Travel {travel_dir} blocked — passable: {', '.join(alts) or 'none'} (find a detour)")
            # Indoors: surface the door/stairs tiles so the agent can leave. The
            # outdoor route is unreachable until it does (see get_route_guidance).
            if tilemap.ready and infer_building_type(state.map_bank, state.map_id) == "interior":
                warps = tilemap.read_warps()
                if warps:
                    px, py = state.player_x, state.player_y
                    nearest = min(warps, key=lambda w: abs(w[0] - px) + abs(w[1] - py))
                    steps = []
                    if nearest[1] > py:   steps.append(f"{nearest[1]-py} Down")
                    elif nearest[1] < py: steps.append(f"{py-nearest[1]} Up")
                    if nearest[0] > px:   steps.append(f"{nearest[0]-px} Right")
                    elif nearest[0] < px: steps.append(f"{px-nearest[0]} Left")
                    toward = ", then ".join(steps) if steps else "you are next to it — step onto it"
                    coords = ", ".join(f"({x},{y})" for x, y in warps[:4])
                    obs_parts.append(
                        f"EXITS (door/stairs tiles): {coords}. To leave the building, "
                        f"call walk_to{nearest} — it will path there and step through. "
                        f"(Nearest is {nearest}: {toward}.)")
            # Outdoors: surface map connections (which edge leads to which map).
            # These are seamless — walk off that edge to cross; not warp tiles.
            elif tilemap.ready and state.context == GameContext.OVERWORLD:
                conns = tilemap.read_connections()
                if conns:
                    parts = []
                    for c in conns:
                        name = MAP_NAMES.get((c["map_bank"], c["map_id"]),
                                             f"{c['map_bank']}/{c['map_id']}")
                        parts.append(f"{c['direction']}→{name}")
                    obs_parts.append("Map edges (call go_to_map(direction) to travel there): "
                                     + ", ".join(parts))
            if diff.notes:
                obs_parts.append("Changes: " + "; ".join(diff.notes))
            # Revisit warning — explicit signal to explore new directions
            visits = stm.visit_count(state.player_x, state.player_y)
            if visits >= 4 and state.context == GameContext.OVERWORLD:
                obs_parts.append(
                    f"REVISIT #{visits}: you have been at ({state.player_x},{state.player_y}) "
                    f"{visits} times — choose a direction you have NOT tried recently"
                )

            if stm.stuck:
                ctx = state.context.name
                if ctx == "IN_BATTLE":
                    obs_parts.append("STUCK: same battle action repeating — try a different move or switch Pokémon")
                elif ctx == "DIALOG_OPEN" or ctx == "TRANSITIONING":
                    obs_parts.append("STUCK: dialog/transition not advancing — press A")
                elif ctx == "IN_MENU":
                    obs_parts.append("STUCK in a menu — press B to close it and return to the field, or navigate with the D-pad and A")
                else:
                    obs_parts.append("STUCK: position unchanged after repeated input — wall or obstacle ahead, try a different direction or press B to cancel any open menu")
                    # Re-inject the area map when stuck on the overworld so the agent can re-orient
                    if USE_VISION and pending_map_b64 is None:
                        pending_map_b64, pending_map_name = AgentClient.load_area_map(*map_key)

            # Close every turn with an explicit call to action — the state dump
            # alone reads to some models as "no question asked", and they reply
            # with prose instead of acting. Make the imperative unmissable.
            obs_parts.append("→ Your turn: decide the best next action and call a tool NOW (do not reply with text only)")
            obs = " | ".join(obs_parts)
            console.print(f"[yellow]OBS:[/] {obs[:140]}")

            # ── Blackout check ───────────────────────────────────────────────
            if state.party and all(p.current_hp == 0 for p in state.party):
                console.print("[red bold]BLACKOUT — all party fainted, loading save state[/]")
                reward.reward("loss")
                ltm.save()
                mgba.load_state(0)
                mgba.tick(60)
                prev_state = None
                battle_was_active = False
                continue

            # ── LLM decision step ────────────────────────────────────────────
            client.set_system(build_system_prompt(ltm, journal, state,
                                                   current_enemy=current_enemy))
            screenshot = client.capture_screenshot() if USE_VISION else None
            reasoning, actions = client.step(obs, screenshot,
                                             area_map_b64=pending_map_b64,
                                             area_map_name=pending_map_name)
            # Map is attached on entry only — clear so it won't repeat next tick
            pending_map_b64 = None
            pending_map_name = ""
            if actions:
                stm.record_action(";".join(actions), state.player_x, state.player_y)
            elif reasoning:
                stm.record_action(reasoning[:80], state.player_x, state.player_y)
            if reasoning:
                console.print(f"[dim]{reasoning[:160]}[/]")

            # Sync opponent name back from client (set via set_opponent tool)
            if client._current_opponent:
                current_enemy = client._current_opponent
            # Clear on battle end
            if not in_battle:
                client._current_opponent = ""

            prev_state = state
            mgba.tick()

            step_count += 1
            if MAX_STEPS and step_count >= MAX_STEPS:
                console.print(f"[green]Reached MAX_STEPS={MAX_STEPS} — stopping. "
                              f"Total reward: {reward.total:.1f}[/]")
                ltm.save()
                break

        except KeyboardInterrupt:
            console.print("\n[red]Stopped.")
            ltm.save()
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            time.sleep(1.0)


if __name__ == "__main__":
    main()
