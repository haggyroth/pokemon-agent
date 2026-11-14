"""Experience ↔ level (pure). Box Pokémon store only their experience points, so a PC box listing needs the
growth formulas (from the decomp's gExperienceTables) to show a level."""
from knowledge.growth_data import GROWTH_RATE


def exp_for_level(rate: int, n: int) -> int:
    c = n ** 3
    if rate == 0:
        return c
    if rate == 1:                                    # erratic
        if n <= 50:
            return (100 - n) * c // 50
        if n <= 68:
            return (150 - n) * c // 100
        if n <= 98:
            return ((1911 - 10 * n) // 3) * c // 500
        return (160 - n) * c // 100
    if rate == 2:                                    # fluctuating
        if n <= 15:
            return ((n + 1) // 3 + 24) * c // 50
        if n <= 36:
            return (n + 14) * c // 50
        return ((n // 2) + 32) * c // 50
    if rate == 3:                                    # medium slow
        return 6 * c // 5 - 15 * n * n + 100 * n - 140
    if rate == 4:                                    # fast
        return 4 * c // 5
    return 5 * c // 4                                # slow


def level_from_exp(species_id: int, exp: int) -> int:
    rate = GROWTH_RATE.get(species_id, 0)
    lvl = 1
    for n in range(2, 101):
        if exp >= exp_for_level(rate, n):
            lvl = n
        else:
            break
    return lvl
