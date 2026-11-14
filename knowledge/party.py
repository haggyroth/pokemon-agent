"""Team-balance rules (pure): every Pokémon should be within ~15% of the top level."""
import math

BALANCE_RATIO = 0.85


def min_level_for(top: int) -> int:
    """Lowest acceptable level when the top party level is `top` (ceil(0.85 * top))."""
    return max(1, math.ceil(top * BALANCE_RATIO))


def lagging_mons(party) -> list:
    """[(index, mon)] of ALIVE members below the balance floor, lowest level first. A party of
    fewer than two has nothing to balance."""
    if len(party) < 2:
        return []
    need = min_level_for(max(p.level for p in party))
    lag = [(i, p) for i, p in enumerate(party) if p.level < need and p.current_hp > 0]
    return sorted(lag, key=lambda ip: (ip[1].level, ip[0]))


# ── PP awareness ────────────────────────────────────────────────────────────────
def attack_pp(mon) -> int:
    """Total PP left across `mon`'s DAMAGING moves (a status move like Growl/Harden never counts: a
    mon that only has those cannot make progress in a fight, however much PP they have)."""
    from knowledge.leafgreen_data import MOVE_POWER
    names = getattr(mon, "move_names", None) or []
    pps = getattr(mon, "pp", None) or []
    return sum(p for n, p in zip(names, pps) if n and p > 0 and MOVE_POWER.get(n, 0) > 0)


def can_attack(mon) -> bool:
    """True if `mon` has at least one damaging move with PP left."""
    return attack_pp(mon) > 0


def healthy_enough(mon, floor: float = 0.35) -> bool:
    return bool(mon.max_hp) and mon.current_hp > 0 and mon.current_hp / mon.max_hp >= floor


def party_needs_restock(party, hp_floor: float = 0.35, pp_floor: int = 2) -> str:
    """'' if the team can keep fighting, else why not. The CLOSER is the strongest healthy mon that
    can still attack; it must have more than `pp_floor` attack PP, or the next wild fight can end
    in a spam-the-status-move stalemate."""
    alive = [p for p in party if healthy_enough(p, hp_floor)]
    if not alive:
        return "everyone is hurt"
    strikers = [p for p in alive if can_attack(p)]
    if not strikers:
        return "no healthy Pokémon has attacking PP left"
    best = max(strikers, key=lambda p: (p.level, attack_pp(p)))
    if attack_pp(best) <= pp_floor:
        return f"{best.species_name or 'your best attacker'} is nearly out of attack PP"
    return ""
