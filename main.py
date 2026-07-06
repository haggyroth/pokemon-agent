from datetime import datetime
from config import MGBA_BACKEND
from game.memory_reader import LeafGreenReader
from game.state import GameContext
from game.tilemap_reader import TilemapReader
from agent.lm_studio_client import AgentClient
from agent.reward import RewardTracker
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.battle_journal import BattleJournal, BattleRecord
from knowledge.system_prompt import build_system_prompt
from knowledge.navigation import get_travel_direction, DIRECTION_BUTTON, MAP_NAMES
from knowledge.leafgreen_data import BADGE_BIT_MILESTONE, GYMS
from game.constants import Addr
from knowledge.battle import battle_summary
from rich.console import Console
import time, sys

console = Console()


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
    prev_map_key         = None
    transitioning_steps  = 0
    pending_map_b64      = None   # area map to attach next tick (cleared after one use)
    pending_map_name     = ""

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
                current_enemy = ""
                client._current_opponent = ""

            # ── Battle end detection ────────────────────────────────────────
            if battle_was_active and not in_battle:
                lead_hp_pct = state.party[0].hp_percent if state.party else 0.0
                all_fainted = bool(state.party) and all(p.current_hp == 0 for p in state.party)
                outcome = "loss" if all_fainted else "win"
                # Pass enemy name for journal + system prompt loss-lessons
                current_enemy_snap = current_enemy
                current_enemy = ""
                if outcome == "win":
                    ltm.data["battles_won"] += 1
                else:
                    ltm.data["battles_lost"] += 1
                location = MAP_NAMES.get((state.map_bank, state.map_id),
                                         f"bank={state.map_bank},id={state.map_id}")
                journal.log(BattleRecord(
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    location=location,
                    enemy_name=current_enemy_snap or "unknown",
                    enemy_level=0,
                    player_lead=battle_start_lead,
                    outcome=outcome,
                    turns=0,
                    moves_used=[],
                    hp_remaining_pct=round(lead_hp_pct, 2),
                    reward=0.0,
                    notes="",
                ))
                console.print(f"[magenta]Battle {outcome}[/] | lead={battle_start_lead} hp={lead_hp_pct:.0%}")
                ltm.save()
            # Save the pre-update value so the auto-tap guard below can see
            # whether we were in battle on the PREVIOUS tick (battle_was_active
            # is about to be overwritten with the current tick's value).
            was_in_battle_prev_tick = battle_was_active
            battle_was_active = in_battle

            # Auto-advance dialog during stuck NPC/item transitions.
            # Guards:
            #   • not in_battle            — don't tap during a battle turn
            #   • not was_in_battle_prev_tick — don't tap on the first tick after
            #                                  leaving IN_BATTLE; context can read
            #                                  TRANSITIONING during post-battle
            #                                  animations and turn-change fades
            if (state.context == GameContext.TRANSITIONING
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
                    bsummary = battle_summary(move_names, current_enemy,
                                              lead.hp_percent, lead.pp)
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
                else:
                    obs_parts.append("STUCK: position unchanged after repeated input — wall or obstacle ahead, try a different direction or press B to cancel any open menu")
                    # Re-inject the area map when stuck on the overworld so the agent can re-orient
                    if pending_map_b64 is None:
                        pending_map_b64, pending_map_name = AgentClient.load_area_map(*map_key)

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
            client.set_system(build_system_prompt(ltm, journal, state))
            screenshot = client.capture_screenshot()
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

        except KeyboardInterrupt:
            console.print("\n[red]Stopped.")
            ltm.save()
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            time.sleep(1.0)


if __name__ == "__main__":
    main()
