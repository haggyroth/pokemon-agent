# Battle analysis helpers for the observation string.
# No I/O. Pure functions over POKEMON_TYPES, MOVE_TYPE, GEN3_CATEGORY,
# and the TYPE_CHART.
from __future__ import annotations
from knowledge.type_chart import get_effectiveness
from knowledge.leafgreen_data import (
    POKEMON_TYPES, MOVE_TYPE, GEN3_CATEGORY, STATUS_MOVES,
    MOVE_POWER, MOVE_POWER_DEFAULT,
)


def _type_label(t: str) -> str:
    NAMES = {
        "NOR": "Normal", "FIR": "Fire",    "WAT": "Water", "ELE": "Electric",
        "GRS": "Grass",  "ICE": "Ice",     "FIG": "Fight", "POI": "Poison",
        "GRD": "Ground", "FLY": "Flying",  "PSY": "Psychic","BUG": "Bug",
        "ROC": "Rock",   "GHO": "Ghost",   "DRG": "Dragon", "DRK": "Dark",
        "STL": "Steel",
    }
    return NAMES.get(t, t)


def effectiveness_vs(move_type: str, defender_types: tuple[str, ...]) -> float:
    """Combined multiplier for move_type hitting a Pokemon with the given types."""
    mult = 1.0
    for dt in defender_types:
        mult *= get_effectiveness(move_type, dt)
    return mult


def annotate_moves(move_names: list[str],
                   opponent_name: str = "",
                   pp_list: list[int] | None = None,
                   opp_statused: bool = False) -> str:
    """Return a compact summary of each move with slot number, type, damage
    category, PP remaining, and effectiveness vs the opponent.

    Format: [N]Name[Type/Cat ×mult PP:cur] or [N]Name[Type/Cat PP:cur] if unknown.
    Moves with PP=0 are flagged NO PP — they cannot be selected. When the opponent
    already has a major status, status-inflicting moves are flagged WON'T STICK.
    ×0=immune  ×0.5=not very  ×1=normal  ×2=super  ×4=super super
    """
    from knowledge.leafgreen_data import STATUS_INFLICTING_MOVES
    opp_types = POKEMON_TYPES.get(opponent_name.upper().strip())

    parts: list[str] = []
    for idx, name in enumerate(move_names):
        slot = idx + 1
        if not name:
            continue

        pp_cur = pp_list[idx] if (pp_list and idx < len(pp_list)) else None
        pp_tag = ""
        if pp_cur is not None:
            pp_tag = f" PP:{pp_cur}" + (" NO PP" if pp_cur == 0 else "")
        if opp_statused and name in STATUS_INFLICTING_MOVES:
            pp_tag += " WON'T STICK (already statused)"

        mtype = MOVE_TYPE.get(name)
        if mtype is None:
            parts.append(f"[{slot}]{name}[?{pp_tag}]")
            continue
        category = GEN3_CATEGORY.get(mtype, "?")
        cat_short = "Phys" if category == "Physical" else "Spec"

        if opp_types:
            mult = effectiveness_vs(mtype, opp_types)
            if mult == 0:
                eff = "×0 IMMUNE"
            elif mult < 1:
                eff = f"×{mult:.1g} weak"
            elif mult == 1:
                eff = "×1"
            elif mult == 2:
                eff = "×2 SUPER"
            else:
                eff = f"×{mult:.0f} SUPER"
            parts.append(f"[{slot}]{name}[{_type_label(mtype)}/{cat_short} {eff}{pp_tag}]")
        else:
            parts.append(f"[{slot}]{name}[{_type_label(mtype)}/{cat_short}{pp_tag}]")

    return "  ".join(parts)


def _has_major_status(status: str) -> bool:
    """True if the opponent already carries a major status (sleep/poison/paralysis/
    burn/freeze) — from decode_status(). 'healthy'/'unknown'/'' are not statuses."""
    s = (status or "").lower()
    return any(k in s for k in ("asleep", "sleep", "poison", "paralyz", "burn", "frozen", "freeze"))


def battle_summary(move_names: list[str],
                   opponent_name: str,
                   player_hp_pct: float,
                   pp_list: list[int] | None = None,
                   attacker_types: tuple[str, ...] = (),
                   opponent_status: str = "") -> str:
    """Full battle analysis block injected into the obs string during IN_BATTLE.

    `attacker_types` (the acting Pokémon's types) enables a STAB bonus when
    ranking the best move. `opponent_status` (from decode_status) drives the
    "don't re-apply a status" guidance.
    """
    lines: list[str] = []

    opp_types = POKEMON_TYPES.get(opponent_name.upper().strip())
    status_tag = ""
    opp_statused = _has_major_status(opponent_status)
    if opp_statused:
        status_tag = f" — {opponent_status.upper()}"
    if opp_types:
        type_str = "/".join(_type_label(t) for t in opp_types)
        lines.append(f"Opponent: {opponent_name} [{type_str}]{status_tag}")
    else:
        lines.append(f"Opponent: {opponent_name} [type unknown — read screenshot]{status_tag}")

    lines.append(f"Your moves: {annotate_moves(move_names, opponent_name, pp_list, opp_statused)}")

    if opp_types:
        # Suggest the best *damaging* move, ranked by an approximate expected
        # damage: base power × STAB × type effectiveness. Skip 0-PP moves and
        # known status (non-damaging) moves so e.g. Growl is never proposed, and
        # so a strong neutral move can outrank a weak super-effective one.
        scored = []
        for idx, name in enumerate(move_names):
            if not name or name in STATUS_MOVES:
                continue
            if pp_list and idx < len(pp_list) and pp_list[idx] == 0:
                continue  # can't use — no PP
            mt = MOVE_TYPE.get(name)
            if mt:
                eff = effectiveness_vs(mt, opp_types)
                stab = 1.5 if mt in attacker_types else 1.0
                power = MOVE_POWER.get(name, MOVE_POWER_DEFAULT)
                scored.append((power * stab * eff, eff, name))
        best_move = None
        if scored:
            scored.sort(reverse=True)
            _score, best_eff, best_move = scored[0]
            if best_eff >= 2:
                lines.append(f"Best move: {best_move} (×{best_eff:.0f} super effective)")
            elif best_eff == 1:
                lines.append(f"Best move: {best_move} (no super effective option)")
            elif best_eff == 0:
                lines.append("WARNING: all damaging moves immune to opponent — consider switching")
        elif pp_list and all(p == 0 for p in pp_list if p is not None):
            lines.append("WARNING: all moves have 0 PP — Struggle will be used automatically")
        # If the opponent is ALREADY statused, a second status move is wasted —
        # steer hard to a damaging attack (the agent looped Sleep Powder for turns).
        if opp_statused:
            steer = f" — attack with {best_move}" if best_move else ""
            lines.append(
                f"NOTE: opponent is already {opponent_status.upper()} — do NOT use a "
                f"status move (Sleep Powder, Poison Powder, Thunder Wave, etc.); it "
                f"will FAIL. Use a DAMAGING move{steer}.")

    if player_hp_pct < 0.30:
        lines.append(f"WARNING: HP at {player_hp_pct:.0%} — consider healing (Start > Bag) or using a Potion")

    return " | ".join(lines)
