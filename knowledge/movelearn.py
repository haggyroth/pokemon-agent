"""Level-up move-learn policy: which of the current 4 moves (if any) to forget when the game offers a new one.
Pure/testable. Each move gets a VALUE — damaging moves by base power (×1.5 with same-type attack bonus, discounted
for two-turn moves), status moves by how useful they actually are (sleep/paralysis/recovery/set-up ≫ Growl) — and the
new move is learned when it is clearly better than the least valuable move that may be forgotten.

Hard rules (from real runs):
  1. NEVER cripple the moveset: always keep at least two damaging moves (one if that is all we have).
  2. HM moves (Cut, Surf, …) can't be forgotten in the game's own delete screen, so they are never chosen.

`choose_move_to_forget` returns the slot index (0-3) to forget, or None to DECLINE.
"""
from knowledge.leafgreen_data import MOVE_POWER, MOVE_POWER_DEFAULT, MOVE_TYPE, STATUS_MOVES

HM_MOVES = frozenset({"Cut", "Fly", "Surf", "Strength", "Flash", "Rock Smash", "Waterfall", "Dive"})
MARGIN = 5                       # the new move must beat the forgotten one by this much
_TWO_TURN = frozenset({"Solar Beam", "SolarBeam", "Hyper Beam", "Sky Attack", "Skull Bash", "Razor Wind",
                       "Dig", "Fly", "Bounce", "Dive"})

_STATUS_VALUE = {
    # put to sleep / paralyse / disable the foe
    **dict.fromkeys(("Sleep Powder", "Spore", "Hypnosis", "Lovely Kiss", "Sing", "Grass Whistle"), 45),
    **dict.fromkeys(("Thunder Wave", "Stun Spore", "Glare"), 40),
    **dict.fromkeys(("Toxic", "Poison Powder", "Poison Gas", "Will-O-Wisp", "Confuse Ray", "Supersonic"), 25),
    "Leech Seed": 30,
    # recovery / set-up
    **dict.fromkeys(("Recover", "Softboiled", "Soft-Boiled", "Rest", "Synthesis", "Moonlight", "Morning Sun",
                     "Milk Drink"), 40),
    **dict.fromkeys(("Swords Dance", "Growth", "Dragon Dance", "Calm Mind", "Bulk Up", "Agility", "Amnesia"), 35),
    **dict.fromkeys(("Double Team", "Minimize", "Reflect", "Light Screen", "Substitute", "Protect", "Detect",
                     "Endure", "Mean Look", "Spider Web", "Focus Energy"), 20),
    # minor stat nudges
    **dict.fromkeys(("Growl", "Tail Whip", "Leer", "String Shot", "Sand-Attack", "Smokescreen", "Screech",
                     "Harden", "Withdraw", "Defense Curl", "Flash", "Sweet Scent", "Kinesis", "Charm",
                     "FeatherDance", "Feather Dance", "Scary Face", "Splash", "Teleport", "Metal Sound",
                     "Cotton Spore"), 5),
}


def _is_damaging(name: str) -> bool:
    return bool(name) and name not in STATUS_MOVES and MOVE_POWER.get(name, MOVE_POWER_DEFAULT) > 0


def move_value(name: str, own_types=()) -> float:
    """How much a move is worth to this Pokémon: 0 for an empty slot, attack power (×1.5 for the user's own
    type, ×0.65 for two-turn moves) for damaging moves, a utility score for status moves."""
    if not name:
        return 0.0
    if not _is_damaging(name):
        return float(_STATUS_VALUE.get(name, 12))
    v = float(MOVE_POWER.get(name, MOVE_POWER_DEFAULT))
    if MOVE_TYPE.get(name) in own_types:
        v *= 1.5
    if name in _TWO_TURN:
        v *= 0.65
    return v


def choose_move_to_forget(current_names: list[str], new_name: str, own_types=()) -> int | None:
    """Slot (0-3) to forget so `new_name` can be learned, or None to decline (keep the current moves)."""
    if len(current_names) != 4:
        return None
    new_v = move_value(new_name, own_types)
    new_dmg = _is_damaging(new_name)
    dmg_now = sum(1 for n in current_names if _is_damaging(n))
    # Candidates: any slot that is not an HM move, cheapest first.
    order = sorted((i for i, n in enumerate(current_names) if n not in HM_MOVES),
                   key=lambda i: (move_value(current_names[i], own_types), i))
    for i in order:
        gone = current_names[i]
        dmg_after = dmg_now - (1 if _is_damaging(gone) else 0) + (1 if new_dmg else 0)
        if dmg_after < min(2, dmg_now + (1 if new_dmg else 0)):
            continue                                   # would leave too few attacks
        if new_v > move_value(gone, own_types) + MARGIN:
            return i
        return None                                    # the cheapest allowed slot isn't worth replacing
    return None
