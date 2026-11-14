"""Catch policy (pure): is this wild Pokémon worth a Poké Ball? (Beating the game is the primary objective;
completing the Pokédex is secondary — a full party still catches brand-new species for it.)

The agent used to catch everything new (an L2 Geodude, a Harden-only Kakuna) and then had to grind it
up from far behind. The rules weigh what a catch COSTS (levels of grinding to get it within ~25% of the
team's top level — see knowledge.party) against what it ADDS (a strong evolution line, a type the team
lacks). The verdict is advice shown to the model and used to decide which wild battles go_to stops on;
the model can still choose to catch anything.
"""
from dataclasses import dataclass

from knowledge.party import min_level_for
from knowledge.species_data import SPECIES_DATA

PREMIUM_LINE = 450        # best evolution ≥ this BST → worth some grinding (Abra, Growlithe, Gastly…)
FREE_DEBT = 3             # levels behind the balance floor we'll accept for any new species
PREMIUM_DEBT = 6          # …and for a premium line
WEAK_LINE = 400           # best evolution below this is only worth it as a type-coverage pickup


@dataclass(frozen=True)
class Verdict:
    catch: bool
    reason: str
    debt: int = 0          # levels the catch would trail the balance floor by


def _team_types(party) -> set:
    from knowledge.leafgreen_data import POKEMON_TYPES
    out = set()
    for p in party:
        out.update(POKEMON_TYPES.get((getattr(p, "species_name", "") or "").upper().strip(), ()))
    return out


def evaluate(party, species_id: int, level: int, max_team: int = 6, dex_owned: bool | None = None) -> Verdict:
    """Verdict for a wild `species_id` at `level` against the current `party`."""
    data = SPECIES_DATA.get(species_id)
    if data is None:
        return Verdict(False, "unknown species")
    bst, types, line_best = data
    if any(p.species_id == species_id for p in party):
        return Verdict(False, "you already have one")
    if len(party) >= max_team:
        if dex_owned is False:
            # Secondary objective: complete the Pokédex. A full party sends the catch to the PC box, where it
            # costs no levelling — worth a ball for the new entry.
            return Verdict(True, "a NEW Pokédex entry (your party is full, so it goes to the PC box)")
        return Verdict(False, "your party is full — it would go to the PC box")
    top = max((p.level for p in party), default=0)
    debt = max(0, min_level_for(top) - level) if top else 0
    premium = line_best >= PREMIUM_LINE
    new_type = bool(set(types) - _team_types(party))

    if debt <= FREE_DEBT and (line_best >= WEAK_LINE or new_type):
        return Verdict(True, "close to your team's level" + (", adds a new type" if new_type else ""), debt)
    if premium and debt <= PREMIUM_DEBT:
        return Verdict(True, f"strong evolution line (best form BST {line_best}); ~{debt} levels of "
                             "training needed", debt)
    if debt > FREE_DEBT:
        return Verdict(False, f"L{level} is {debt} levels under your balance floor (L{min_level_for(top)}) — "
                              "you'd have to grind it up from far behind", debt)
    return Verdict(False, f"weak line (best form BST {line_best}) and it adds no new type", debt)
