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
