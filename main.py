from datetime import datetime
from config import (MGBA_BACKEND, START_FROM_SAVE, START_FROM_STATE, MAX_STEPS,
                    USE_VISION, PROGRESS_PATH, MAX_LLM_CALLS, TOKEN_BUDGET,
                    LLM_BASE_URL, MAX_WALL_SECONDS)
from game.memory_reader import LeafGreenReader
from game.state import GameContext, GameState, active_party_member, newly_fainted_slots
from game.tilemap_reader import TilemapReader
from agent.lm_studio_client import AgentClient
from agent.reward import RewardTracker
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.battle_journal import BattleJournal, BattleRecord
from knowledge.system_prompt import build_system_prompt
from knowledge.navigation import get_travel_direction, DIRECTION_BUTTON, MAP_NAMES, infer_building_type
from knowledge.leafgreen_data import BADGE_BIT_MILESTONE, GYMS, GYM_MAP_LEADER, POKEMON_TYPES
from knowledge.shopping import shopping_summary
from knowledge.map_graph import MAP_KIND
from game.constants import Addr
from game.pathfinding import door_centers
from knowledge.battle import battle_summary, overworld_pp_summary
from rich.console import Console
from dataclasses import dataclass, field
from typing import Callable, Optional
from pathlib import Path
import time, sys, traceback

console = Console()

# Where uncaught per-tick exceptions are recorded (full tracebacks). The console
# only shows a scrolling summary; this file is the durable record for debugging a
# run after the fact. Sits alongside progress.json in the logs dir.
ERRORS_LOG = Path(PROGRESS_PATH).parent / "errors.log"

# Bail out if this many decision ticks fail in a row. A persistent fault (LLM
# endpoint down, poisoned message history, a coding bug) would otherwise spin
# forever at ~1 Hz printing the same line; stopping cleanly saves progress and
# surfaces the failure instead of hiding it.
MAX_CONSECUTIVE_ERRORS = 30


def _log_exception(exc: Exception) -> None:
    """Append a timestamped full traceback to ERRORS_LOG (best-effort)."""
    try:
        ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_LOG, "a") as f:
            f.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} "
                    f"{type(exc).__name__}: {exc} =====\n")
            traceback.print_exc(file=f)
    except Exception:
        pass  # logging must never mask the original error


def _run_summary(reward, client, steps: int) -> str:
    """One-line end-of-run tally: steps, reward, and LLM usage (spend visibility)."""
    return (f"steps={steps}  reward={reward.total:.1f}  "
            f"llm_calls={client.llm_calls}  tokens={client.total_tokens} "
            f"(prompt={client.total_prompt_tokens}, completion={client.total_completion_tokens})")


# A goal predicate: given the live state + long-term memory, has the episode's
# objective been met? Used by the eval harness (run_episode(goal=...)); None for
# an open-ended real run.
Goal = Callable[[GameState, LongTermMemory], bool]


@dataclass
class AgentRuntime:
    """Everything a decision loop needs, built once. Shared by the real run
    (main) and the eval harness so the two never drive the game differently."""
    mgba:    object
    reader:  LeafGreenReader
    client:  AgentClient
    ltm:     LongTermMemory
    stm:     ShortTermMemory
    journal: BattleJournal
    reward:  RewardTracker
    tilemap: TilemapReader


@dataclass
class EpisodeResult:
    """Outcome of one run_episode() call — the eval scorecard for a scenario."""
    reason:            str            # goal | max_steps | max_wall | max_llm_calls | token_budget | interrupted | error_budget
    passed:            bool           # goal predicate satisfied
    steps:             int
    reward:            float
    llm_calls:         int
    prompt_tokens:     int
    completion_tokens: int
    final_map:         tuple[int, int]
    final_pos:         tuple[int, int]
    badges:            int
    milestones:        list[str] = field(default_factory=list)
    stuck_ratio:       float = 0.0    # fraction of overworld decision ticks with no movement
    goal_desc:         str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def summary(self) -> str:
        flag = "PASS" if self.passed else "----"
        return (f"[{flag}] {self.reason}  steps={self.steps}  reward={self.reward:.1f}  "
                f"map={self.final_map} pos={self.final_pos}  badges={self.badges}  "
                f"stuck={self.stuck_ratio:.0%}  llm_calls={self.llm_calls}  "
                f"tokens={self.total_tokens}")

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["total_tokens"] = self.total_tokens
        return d


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


def _has_control(mgba, reader) -> bool:
    """True only if the player actually responds to input — the definitive test
    for *real* overworld control vs. the quest-log recap (which ignores the D-pad
    and only ends on B). The chroma gate alone false-positives on a bright recap
    frame or mid-fade (#79), so we confirm by moving.

    Note the Gen III turn-vs-step rule: the FIRST press of a direction you are not
    already facing only TURNS the character (no tile change); the second press
    steps. So we press each direction TWICE before concluding it didn't move —
    otherwise a real, controllable player reads as stuck. Any axis that steps ⇒
    control; we restore position with two opposite presses (turn, then step).
    """
    if reader.detect_context() != GameContext.OVERWORLD:
        return False
    for mv, back in (("Down", "Up"), ("Right", "Left"), ("Up", "Down"), ("Left", "Right")):
        before = reader.read_player_pos()
        mgba.tap(mv)                          # may only turn to face mv
        if reader.read_player_pos() == before:
            mgba.tap(mv)                      # now step
        if reader.read_player_pos() != before:
            mgba.tap(back)                    # turn back
            mgba.tap(back)                    # step back → restore origin
            return True
    return False


def drive_into_gameplay(mgba, reader, attempts: int = 4) -> bool:
    """Boot from the loaded battery save through the pre-gameplay gates into real
    player control. Returns True once normal gameplay is CONFIRMED (the player
    responds to input), retrying the whole boot up to `attempts` times because the
    recap skip is timing-flaky (#79).

    Two gates, each with its own tell:

      1. **Title screen / Continue menu** — not in the game world yet (map bank
         reads 0). Press A until a map loads (this taps through "PRESS START" and
         selects Continue).
      2. **Quest recap** ("Previously on your quest…") — the trap. It auto-plays a
         desaturated replay of recent events and *masquerades as OVERWORLD*
         (field callback, no fade, no menu), so detect_context() and position
         both lie: the recap even auto-animates the player. Neither A-mashing nor
         waiting escapes it — **B skips it**, and the palette snaps back to full
         color when it clears. We press B until the frame is no longer desaturated
         (see _frame_chroma) AND the player actually responds to input
         (_has_control) — chroma alone isn't enough.
    """
    for _attempt in range(attempts):
        mgba.reset()
        mgba.run_frames(200)                  # boot logos

        for _ in range(80):                   # gate 1: title + Continue → game world
            if mgba.read8(Addr.MAP_BANK) != 0:
                break
            mgba.tap("A")

        for _ in range(120):                  # gate 2: skip the recap with B
            if _frame_chroma(mgba) > _RECAP_CHROMA_CUTOFF:
                mgba.tick(10)                 # let the last transition settle
                if _has_control(mgba, reader):
                    return True               # full color AND input-responsive
            mgba.tap("B")
        # This attempt never reached confirmed control — reset and try again.
    return False                              # budget exhausted; hand off anyway


def build_runtime(*, backend: str = MGBA_BACKEND,
                  start_save: str = START_FROM_SAVE,
                  start_state: str = START_FROM_STATE,
                  ltm_path: Optional[str] = None,
                  journal_path: Optional[str] = None,
                  fresh_session: bool = True,
                  verbose: bool = True) -> Optional[AgentRuntime]:
    """Connect to the emulator, load the requested start point, and build every
    component the decision loop needs. Returns None if the emulator isn't ready.

    ltm_path / journal_path isolate persistent state — the eval harness points
    them at a scratch dir so a scenario never touches the real logs/progress.json.
    """
    def say(msg):
        if verbose:
            console.print(msg)

    if verbose:
        console.rule("[bold green]Pokemon LeafGreen LLM Agent")
    if backend == "native":
        from game.mgba_core import NativeMGBAClient
        mgba = NativeMGBAClient()
    else:
        from game.mgba_client import MGBAClient
        mgba = MGBAClient()
    if not mgba.verify_connection():
        say(f"[red]ERROR: emulator not ready or wrong ROM (backend={backend}).[/]")
        say("Expected AGB-BPGE (Pokemon LeafGreen). Check ROM_PATH / startup order.")
        return None
    say(f"[green]Connected ({backend}): {mgba.get_game_title()} ({mgba.get_game_code()})")

    # Warn on the one config that can run up real money: a non-local LLM endpoint
    # with no stopping condition at all. The run still proceeds (the user may want
    # it), but the cost exposure should be explicit rather than silent.
    _is_local = any(h in LLM_BASE_URL for h in ("localhost", "127.0.0.1", "::1"))
    if not _is_local and not (MAX_STEPS or MAX_LLM_CALLS or TOKEN_BUDGET):
        say(f"[yellow]⚠ Cloud endpoint ({LLM_BASE_URL}) with no run cap "
            f"(MAX_STEPS / MAX_LLM_CALLS / TOKEN_BUDGET all unset) — this "
            f"loop is unbounded and will keep spending until interrupted.[/]")

    reader = LeafGreenReader(mgba, decrypt=True)

    # Optionally load an mGBA save STATE directly — instant, no title/Continue/
    # recap. Takes precedence over start_save (native only).
    if start_state and backend == "native":
        if mgba.load_state_file(start_state):
            mgba.tick(30)   # let post-load fade/flags settle before first read
            s = reader.read_state()
            say(f"[green]Loaded save state: {start_state} "
                f"(map {s.map_bank}/{s.map_id}, pos ({s.player_x},{s.player_y}))[/]")
        else:
            say(f"[red]Could not load save state: {start_state}[/]")
    # Otherwise, optionally boot from a battery save and drive to "Continue" so the
    # agent starts in real gameplay instead of the new-game intro (native only).
    elif start_save and backend == "native":
        if mgba.load_save(start_save):
            got_control = drive_into_gameplay(mgba, reader)
            where = f"map {mgba.read8(Addr.MAP_BANK)}/{mgba.read8(Addr.MAP_ID)}"
            if got_control:
                say(f"[green]Continued from save: {start_save} ({where})[/]")
            else:
                say(f"[yellow]Continued from save but could not confirm player "
                    f"control ({where}) — may still be in the quest recap[/]")
        else:
            say(f"[red]Could not load save: {start_save}[/]")

    tilemap = TilemapReader(mgba)
    ltm     = LongTermMemory(path=ltm_path)
    client  = AgentClient(mgba, reader, ltm)
    stm     = ShortTermMemory()
    journal = BattleJournal(path=journal_path)
    reward  = RewardTracker(shaped=True)

    if fresh_session:
        ltm.new_session()
    say(f"Session #{ltm.data['session_count']} | Badges: {ltm.data['badges_earned']}/8 | "
        f"Milestones: {len(ltm.data['milestones'])}")

    # ── Startup badge reconciliation ─────────────────────────────────────────
    # Sync LTM to EXACTLY match the loaded cartridge's badges (the ground truth for
    # this run) — adopting any the save has AND dropping any the journal claims but
    # the save doesn't. A journal left ahead of the save (e.g. testing an older save,
    # or an in-memory gym win that never hit the cartridge) otherwise deadlocks the
    # agent: it thinks a gym is beaten, heads on, and the game's guard NPC marches it
    # back. Read via the RELOCATION-SAFE reader.read_badges() (NOT the fixed
    # Addr.BADGES). Mid-session stays monotonic so a load_state retry can't un-earn.
    _sync = ltm.reconcile_badges_authoritative(reader.read_badges()[1])
    if _sync["dropped"]:
        say(f"[red bold]⚠ Journal was AHEAD of the save — dropped "
            f"{', '.join(_sync['dropped'])} to match the cartridge "
            f"(badges now {ltm.data['badges_earned']}/8). "
            f"Use `python -m tools.reset_journal` for a full reset.[/]")
    if _sync["adopted"]:
        say(f"[yellow]Adopted from the save into LTM: {', '.join(_sync['adopted'])}[/]")

    return AgentRuntime(mgba=mgba, reader=reader, client=client, ltm=ltm,
                        stm=stm, journal=journal, reward=reward, tilemap=tilemap)


def run_episode(rt: AgentRuntime, *, goal: Optional[Goal] = None, goal_desc: str = "",
                max_steps: int = 0, max_wall_s: float = MAX_WALL_SECONDS,
                verbose: bool = True) -> EpisodeResult:
    """Drive the decision loop until the goal is met, a cap is hit, or the run is
    interrupted / exceeds the error budget. Returns an EpisodeResult scorecard.

    With goal=None and max_steps=0 this is the open-ended real run (what main()
    uses). The eval harness passes a goal predicate + step budget per scenario.
    Spend caps (MAX_LLM_CALLS/TOKEN_BUDGET) always apply as a safety net.
    """
    mgba, reader, client = rt.mgba, rt.reader, rt.client
    ltm, stm, journal, reward, tilemap = rt.ltm, rt.stm, rt.journal, rt.reward, rt.tilemap

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
    wall_deadline        = time.time() + max_wall_s if max_wall_s else 0.0
    consecutive_errors   = 0      # ticks that raised in a row (see MAX_CONSECUTIVE_ERRORS)
    blackout_active      = False  # inside a blackout (all fainted); reset on recovery
    decision_ticks       = 0      # overworld decision ticks (for stuck_ratio)
    stuck_ticks          = 0      # of those, how many with no movement

    def _result(reason: str, passed: bool, s: Optional[GameState] = None) -> EpisodeResult:
        if s is None:
            s = reader.read_state()
        return EpisodeResult(
            reason=reason, passed=passed, steps=step_count,
            reward=round(reward.total, 2), llm_calls=client.llm_calls,
            prompt_tokens=client.total_prompt_tokens,
            completion_tokens=client.total_completion_tokens,
            final_map=(s.map_bank, s.map_id), final_pos=(s.player_x, s.player_y),
            badges=ltm.data["badges_earned"],
            milestones=list(ltm.data.get("milestones", [])),
            stuck_ratio=round(stuck_ticks / decision_ticks, 3) if decision_ticks else 0.0,
            goal_desc=goal_desc,
        )

    while True:
        try:
            # A level-up can trigger an evolution scene on return to the field. It
            # flickers between TRANSITIONING and IN_MENU, so the model kept cancelling
            # it with B and the lead never evolved. Complete it here (advance with A,
            # never B) before anything else acts, so the model never sees it.
            if client._in_evolution_scene():
                client._finish_evolution()
            state = reader.read_state()
            diff  = reader.diff(prev_state, state)
            stm.current_state = state
            stm.last_state    = prev_state
            stm.last_diff     = diff

            # Goal reached? (eval harness only; no-op for the open-ended real run.)
            if goal is not None and goal(state, ltm):
                if verbose:
                    console.print(f"[green bold]GOAL reached: {goal_desc}[/]")
                ltm.save()
                return _result("goal", True, state)

            in_battle = state.context == GameContext.IN_BATTLE
            if in_battle and not battle_was_active:
                stm.reset_for_new_battle()
                ltm.data["total_battles"] += 1
                battle_start_lead = state.party[0].species_name if state.party else ""
                battle_active_slot = 0
                # Classify the battle from gBattleTypeFlags (set at battle init).
                battle_is_trainer = bool(mgba.read32(Addr.BATTLE_TYPE_FLAGS)
                                         & Addr.BATTLE_TYPE_TRAINER)
                # Identify the opponent from memory (gEnemyParty[0]) — do NOT rely
                # on the model to read the species off the screen (it guessed wrong).
                enemy = reader.read_enemy_lead()
                current_enemy = (enemy.species_name or "").upper().strip() if enemy else ""
                client._current_opponent = current_enemy

            # Keep the opponent identity fresh from memory every battle tick (it
            # can load a frame or two after the battle callback, and the lead
            # changes when a trainer sends out its next Pokémon). Memory is
            # authoritative — never let the model's guess override it.
            if in_battle:
                enemy = reader.read_enemy_lead()
                if enemy and enemy.species_name:
                    current_enemy = enemy.species_name.upper().strip()

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
                # Auto-advance a genuine transition/dialog by tapping A. This branch
                # `continue`s BEFORE the step/wall-clock budget checks below, so it must
                # be BOUNDED — a game state stuck in TRANSITIONING would otherwise tap A
                # forever and bypass every guardrail (an eval hung here for hours). The
                # wall-clock cap is enforced inline, and after a cap we fall through so a
                # normal step runs (LLM re-engages + the budgets get checked).
                if wall_deadline and time.time() >= wall_deadline:
                    ltm.save()
                    return _result("max_wall", False, state)
                if 5 <= transitioning_steps < 45:
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

            # Keep the in-memory reward total current; it's written to disk on the
            # next ltm.save() (battle end / milestone / stop), not every tick — so a
            # crash loses reward accrued since the last save (acceptably small).
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
                # Proactive heal nudge: low HP outside battle → recommend heal().
                if (not in_battle and lead.max_hp and lead.hp_percent < 0.40
                        and state.context == GameContext.OVERWORLD):
                    obs_parts.append(
                        f"⚠ Lead HP low ({lead.hp_percent:.0%}) — call heal() to "
                        f"restore the party at the nearest Pokémon Center")
                # Team-building nudge: a lone/pair Pokémon can't sustain a dungeon (its
                # HP + move PP drain with no way to spread the load) or the Elite Four.
                # go_to now stops on new wild species so the model can catch a roster.
                if (not in_battle and state.context == GameContext.OVERWORLD
                        and len(state.party) < 3):
                    roster = ", ".join(f"{p.species_name} L{p.level}"
                                       for p in state.party if p.species_name)
                    obs_parts.append(
                        f"⚠ Team: only {len(state.party)} Pokémon ({roster}) — too few to "
                        "sustain dungeons (Mt. Moon) or the Elite Four. Build to 3-4+: in "
                        "tall grass, weaken a wild Pokémon with use_move, then catch(). "
                        "(Travel stops on NEW species so you can catch them.)")
                # Under-levelled-for-Brock nudge: no badges yet and lead below the
                # ~L13 Vine Whip breakpoint → grind before challenging the gym.
                if (not in_battle and ltm.data["badges_earned"] == 0
                        and lead.level and lead.level < 13
                        and state.context == GameContext.OVERWORLD):
                    obs_parts.append(
                        f"⚠ Lead is L{lead.level} — under-levelled for Brock (want ~L13 "
                        f"for Vine Whip). Stand in tall grass and call grind(13) to level "
                        f"up before the Pewter Gym")
                if in_battle:
                    move_names = [m for m in lead.move_names if m]
                    lead_types = POKEMON_TYPES.get((lead.species_name or "").upper().strip(), ())
                    enemy = reader.read_enemy_lead()
                    bsummary = battle_summary(move_names, current_enemy,
                                              lead.hp_percent, lead.pp,
                                              attacker_types=lead_types,
                                              opponent_status=enemy.status if enemy else "")
                    obs_parts.append(bsummary)
                    if enemy:
                        obs_parts.append(f"Opponent HP: {enemy.current_hp}/{enemy.max_hp} (L{enemy.level})")
                    # Tell the model whether it can flee (wild) or must fight (trainer).
                    if battle_is_trainer:
                        obs_parts.append("TRAINER battle — you cannot flee; win or switch.")
                    else:
                        obs_parts.append("WILD battle — you may flee_battle() to escape "
                                         "if you're just passing through or HP is low.")
                        # Suggest catching a wild Pokémon that would add to the team:
                        # a NEW species (not already in your party) when you have balls.
                        balls = sum(reader.read_bag().get(b, 0) for b in (1, 2, 3, 4))
                        party_species = {p.species_id for p in state.party}
                        if (balls > 0 and enemy and enemy.species_id
                                and enemy.species_id not in party_species
                                and len(state.party) < 6):
                            obs_parts.append(
                                f"NEW SPECIES you don't own ({balls} Poké Balls in bag) — "
                                "consider catch() to add it to your team. Weaken it first "
                                "with use_move (low HP raises the catch rate).")
                        elif balls == 0 and len(state.party) < 6:
                            obs_parts.append(
                                "You have no Poké Balls — buy some with shop() to catch "
                                "wild Pokémon for your team.")
            obs_parts.append(f"Pos: ({state.player_x},{state.player_y}) Map: {state.map_bank}/{state.map_id}")
            # Money + key consumables (for heal/catch/shopping decisions). Cheap
            # reads; only meaningful outside battle transitions.
            if not in_battle and state.context in (GameContext.OVERWORLD, GameContext.IN_MENU):
                money = reader.read_money()
                bag = reader.read_bag()
                balls = sum(bag.get(b, 0) for b in (1, 2, 3, 4))   # any Poké Ball type
                potions = sum(bag.get(p, 0) for p in (13, 22, 21, 20, 19))
                obs_parts.append(
                    f"Bag: ¥{money} | Poké Balls: {balls} | Potions/heals: {potions}")
                # Lead move PP — the agent is otherwise blind to PP outside battle and
                # would run its attacking moves dry across a trainer gauntlet (it did,
                # for 11 hours). A Pokémon Center heal restores PP, so warn while it
                # can still retreat. (In battle the per-move PP is already in the obs.)
                lead = state.party[0] if state.party else None
                if lead:
                    pp_line, pp_warn = overworld_pp_summary(lead.move_names, lead.pp)
                    if pp_line:
                        obs_parts.append(pp_line)
                    if pp_warn:
                        obs_parts.append(pp_warn)
                # At a Mart: recommend a badge-gated, par-level restock the agent can afford.
                if MAP_KIND.get((state.map_bank, state.map_id)) == "mart":
                    rec = shopping_summary(bag, ltm.data["badges_earned"], money)
                    if rec:
                        obs_parts.append(
                            "MART — " + rec + ". Call shop() to buy the recommended "
                            "restock automatically.")
            # Inside a gym: point the agent at the Leader — UNLESS this Leader is
            # already beaten, in which case say so and tell it to leave (the agent
            # looped in/out of Pewter Gym re-challenging Brock). go_to is useless
            # here; you have to WALK UP to the Leader.
            if (not in_battle and state.context == GameContext.OVERWORLD
                    and MAP_KIND.get((state.map_bank, state.map_id)) == "gym"):
                gym_leader = GYM_MAP_LEADER.get((state.map_bank, state.map_id))
                if gym_leader and gym_leader in ltm.data["gyms_beaten"]:
                    obs_parts.append(
                        f"GYM ALREADY BEATEN: you already defeated {gym_leader} here — "
                        "do NOT challenge them again. LEAVE the gym (walk_to the exit "
                        "door) and head to your NEXT objective in the Navigation section.")
                else:
                    obs_parts.append(
                        "GYM: to fight the Leader, call challenge_leader() — it walks up "
                        "to them and starts the battle. (heal() and save_state first.) "
                        "Do NOT use go_to inside a gym.")
            if state.context == GameContext.OVERWORLD and tilemap.ready:
                if tilemap._width and tilemap._height:
                    obs_parts.append(f"Map size: {tilemap._width}×{tilemap._height} "
                                     f"(walk_to needs 0≤x<{tilemap._width}, 0≤y<{tilemap._height})")
                surr = tilemap.surroundings_str(state.player_x, state.player_y)
                obs_parts.append(f"Tiles: {surr}")
                balls = reader.read_item_ball_tiles()
                if balls:
                    where = ", ".join(f"({x},{y})" for x, y in balls[:5])
                    obs_parts.append(
                        f"Items on the ground: item ball(s) at {where} — call "
                        "pick_up_items() to collect them before leaving.")
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
                # A door can span several adjacent warp tiles but usually only the
                # CENTER one actually warps (the side tiles "arrive" without exiting).
                # Collapse each contiguous run to its middle so we point at the tile
                # that works (fixes suggesting an off-by-one non-functional door).
                warps = door_centers(tilemap.read_warps())
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
            if verbose:
                console.print(f"[yellow]OBS:[/] {obs[:140]}")

            # ── Blackout check ───────────────────────────────────────────────
            party_wiped = bool(state.party) and all(p.current_hp == 0 for p in state.party)
            if not party_wiped:
                blackout_active = False   # recovered (respawn/heal) → re-arm
            if party_wiped:
                # Fire the loss penalty ONCE per blackout, not every tick while the
                # party stays fainted (that double-counted the penalty indefinitely).
                if not blackout_active:
                    blackout_active = True
                    console.print("[red bold]BLACKOUT — all party fainted[/]")
                    reward.reward("loss")
                    ltm.save()
                # Try to reload the pre-fight state. If none was saved this session
                # the load FAILS (slot file missing) — don't pretend it worked and
                # spin; let the game's own whiteout sequence carry the player to the
                # last Pokémon Center by advancing its dialog with A.
                if mgba.load_state(0):
                    console.print("[green]Loaded slot 0 after blackout[/]")
                    mgba.tick(60)
                    prev_state = None
                    battle_was_active = False
                    blackout_active = False   # recovered via reload
                else:
                    console.print("[yellow]No save state in slot 0 — advancing the "
                                  "whiteout/Nurse-Joy recovery to the Pokémon Center[/]")
                    # The blackout plays a multi-box sequence (out of Pokémon →
                    # scurried to a Center → warp → auto-heal) that only advances on
                    # A. Press it several times per pass (not once) so recovery
                    # actually progresses instead of crawling one box per tick.
                    for _ in range(6):
                        mgba.tap("A")
                        mgba.tick(12)
                        if bool(reader.read_party()) and any(
                                p.current_hp > 0 for p in reader.read_party()):
                            break   # auto-heal landed — party revived
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
            if reasoning and verbose:
                console.print(f"[dim]{reasoning[:160]}[/]")

            # set_opponent is now only a fallback — memory (read_enemy_lead) is
            # authoritative and refreshed each tick above. Use the tool's value
            # only if we somehow couldn't read the opponent from memory.
            if not current_enemy and client._current_opponent:
                current_enemy = client._current_opponent
            # Clear on battle end
            if not in_battle:
                client._current_opponent = ""

            # A full decision tick completed without raising — reset the
            # consecutive-error budget. (The transition/blackout `continue` paths
            # above don't reach here, but they don't raise either, so the counter
            # simply holds; only a real exception grows it.)
            consecutive_errors = 0

            # Stuck tracking: an overworld decision tick that didn't move the
            # player. A high ratio is the signature of the Route-2 "can't cross"
            # thrash — surfaced as EpisodeResult.stuck_ratio for the eval harness.
            if state.context == GameContext.OVERWORLD:
                decision_ticks += 1
                if prev_state is not None and \
                        (state.player_x, state.player_y) == (prev_state.player_x, prev_state.player_y):
                    stuck_ticks += 1

            prev_state = state
            mgba.tick()

            step_count += 1
            if max_steps and step_count >= max_steps:
                if verbose:
                    console.print(f"[green]Reached max_steps={max_steps} — stopping. "
                                  f"{_run_summary(reward, client, step_count)}[/]")
                ltm.save()
                return _result("max_steps", False, state)
            # Spend guards (matter for cloud endpoints; 0 = unlimited). Stop
            # cleanly, same as max_steps, so an unattended run can't run up an
            # unbounded bill.
            if MAX_LLM_CALLS and client.llm_calls >= MAX_LLM_CALLS:
                if verbose:
                    console.print(f"[green]Reached MAX_LLM_CALLS={MAX_LLM_CALLS} — stopping. "
                                  f"{_run_summary(reward, client, step_count)}[/]")
                ltm.save()
                return _result("max_llm_calls", False, state)
            if TOKEN_BUDGET and client.total_tokens >= TOKEN_BUDGET:
                if verbose:
                    console.print(f"[green]Reached TOKEN_BUDGET={TOKEN_BUDGET} — stopping. "
                                  f"{_run_summary(reward, client, step_count)}[/]")
                ltm.save()
                return _result("token_budget", False, state)
            # Wall-clock guard: an unattended run (esp. a local model that degrades on a
            # marathon) can't hang for hours — checked each step, so at worst one over-
            # long step past the deadline (LLM_TIMEOUT bounds that single step).
            if wall_deadline and time.time() >= wall_deadline:
                if verbose:
                    console.print(f"[green]Reached wall-clock cap ({max_wall_s:.0f}s) — stopping. "
                                  f"{_run_summary(reward, client, step_count)}[/]")
                ltm.save()
                return _result("max_wall", False, state)

        except KeyboardInterrupt:
            if verbose:
                console.print(f"\n[red]Stopped.[/] {_run_summary(reward, client, step_count)}")
            ltm.save()
            return _result("interrupted", False)
        except Exception as e:
            consecutive_errors += 1
            _log_exception(e)
            if verbose:
                console.print(f"[red]Error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): "
                              f"{type(e).__name__}: {e}[/] — see {ERRORS_LOG}")
                console.print_exception(max_frames=4)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                if verbose:
                    console.print(f"[red bold]{consecutive_errors} consecutive errors — "
                                  f"stopping. Full tracebacks in {ERRORS_LOG}. "
                                  f"{_run_summary(reward, client, step_count)}[/]")
                ltm.save()
                return _result("error_budget", False)
            time.sleep(1.0)


def main():
    rt = build_runtime(verbose=True)
    if rt is None:
        sys.exit(1)
    result = run_episode(rt, max_steps=MAX_STEPS, verbose=True)
    # run_episode already printed the stop line. Propagate a hard failure as a
    # non-zero exit so a wrapping shell/CI notices the error-budget abort.
    if result.reason == "error_budget":
        sys.exit(1)


if __name__ == "__main__":
    main()
