# Gen III type effectiveness chart (no Fairy type).
# Only non-1.0 entries are stored; get_effectiveness() returns 1.0 by default.
# Keys: NOR FIR WAT ELE GRS ICE FIG POI GRD FLY PSY BUG ROC GHO DRG DRK STL

# TYPE_CHART[attacker][defender] = multiplier  (0, 0.5, or 2.0)
TYPE_CHART: dict[str, dict[str, float]] = {
    "NOR": {"ROC": 0.5, "GHO": 0,   "STL": 0.5},
    "FIR": {"FIR": 0.5, "WAT": 0.5, "GRS": 2.0, "ICE": 2.0, "BUG": 2.0, "ROC": 0.5, "DRG": 0.5, "STL": 2.0},
    "WAT": {"FIR": 2.0, "WAT": 0.5, "GRS": 0.5, "GRD": 2.0, "ROC": 2.0, "DRG": 0.5},
    "ELE": {"WAT": 2.0, "ELE": 0.5, "GRS": 0.5, "GRD": 0,   "FLY": 2.0, "DRG": 0.5},
    "GRS": {"FIR": 0.5, "WAT": 2.0, "GRS": 0.5, "POI": 0.5, "GRD": 2.0, "FLY": 0.5,
            "BUG": 0.5, "ROC": 2.0, "DRG": 0.5, "STL": 0.5},
    "ICE": {"FIR": 0.5, "WAT": 0.5, "GRS": 2.0, "ICE": 0.5, "GRD": 2.0, "FLY": 2.0,
            "DRG": 2.0, "STL": 0.5},
    "FIG": {"NOR": 2.0, "ICE": 2.0, "POI": 0.5, "FLY": 0.5, "PSY": 0.5, "BUG": 0.5,
            "ROC": 2.0, "GHO": 0,   "DRK": 2.0, "STL": 2.0},
    "POI": {"GRS": 2.0, "POI": 0.5, "GRD": 0.5, "ROC": 0.5, "GHO": 0.5, "STL": 0},
    "GRD": {"FIR": 2.0, "ELE": 2.0, "GRS": 0.5, "POI": 2.0, "FLY": 0,   "BUG": 0.5,
            "ROC": 2.0, "STL": 2.0},
    "FLY": {"ELE": 0.5, "GRS": 2.0, "FIG": 2.0, "BUG": 2.0, "ROC": 0.5, "STL": 0.5},
    "PSY": {"FIG": 2.0, "POI": 2.0, "PSY": 0.5, "DRK": 0,   "STL": 0.5},
    "BUG": {"FIR": 0.5, "GRS": 2.0, "FIG": 0.5, "POI": 0.5, "FLY": 0.5, "PSY": 2.0,
            "GHO": 0.5, "DRK": 2.0, "STL": 0.5},
    "ROC": {"FIR": 2.0, "ICE": 2.0, "FIG": 0.5, "GRD": 0.5, "FLY": 2.0, "BUG": 2.0,
            "STL": 0.5},
    "GHO": {"NOR": 0,   "PSY": 2.0, "GHO": 2.0, "DRK": 0.5, "STL": 0.5},
    "DRG": {"DRG": 2.0, "STL": 0.5},
    "DRK": {"FIG": 0.5, "PSY": 2.0, "GHO": 2.0, "DRK": 0.5, "STL": 0.5},
    "STL": {"FIR": 0.5, "WAT": 0.5, "ELE": 0.5, "ICE": 2.0, "ROC": 2.0, "STL": 0.5},
}


def get_effectiveness(attacking_type: str, defending_type: str) -> float:
    """Return damage multiplier for an attacking type vs a defending type.
    Returns 0 (immune), 0.5 (not very effective), 1.0 (normal), or 2.0 (super effective).
    Types use 3-letter codes: NOR FIR WAT ELE GRS ICE FIG POI GRD FLY PSY BUG ROC GHO DRG DRK STL
    """
    return TYPE_CHART.get(attacking_type, {}).get(defending_type, 1.0)


def best_move_type(attacking_types: list[str], defending_types: list[str]) -> tuple[str, float]:
    """Return the attacking type with the highest combined multiplier against all defending types.
    Useful for choosing move type when opponent has multiple types.
    Returns (best_type, multiplier).
    """
    best = ("NOR", 1.0)
    for atk in attacking_types:
        mult = 1.0
        for def_ in defending_types:
            mult *= get_effectiveness(atk, def_)
        if mult > best[1]:
            best = (atk, mult)
    return best
