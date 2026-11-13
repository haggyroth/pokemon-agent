"""TM/HM tables (pure data + policy; no I/O). Item ids per pokefirered constants/items.h:
TM01..TM50 = 289..338, HM01..HM08 = 339..346. Names resolve to move ids via game.constants."""
from game.constants import MOVE_NAMES

TM_MOVES = ["Focus Punch", "Dragon Claw", "Water Pulse", "Calm Mind", "Roar", "Toxic", "Hail",
            "Bulk Up", "Bullet Seed", "Hidden Power", "Sunny Day", "Taunt", "Ice Beam", "Blizzard",
            "Hyper Beam", "Light Screen", "Protect", "Rain Dance", "Giga Drain", "Safeguard",
            "Frustration", "Solar Beam", "Iron Tail", "Thunderbolt", "Thunder", "Earthquake",
            "Return", "Dig", "Psychic", "Shadow Ball", "Brick Break", "Double Team", "Reflect",
            "Shock Wave", "Flamethrower", "Sludge Bomb", "Sandstorm", "Fire Blast", "Rock Tomb",
            "Aerial Ace", "Torment", "Facade", "Secret Power", "Rest", "Attract", "Thief",
            "Steel Wing", "Skill Swap", "Snatch", "Overheat"]
HM_MOVES = ["Cut", "Fly", "Surf", "Strength", "Flash", "Rock Smash", "Waterfall", "Dive"]
ITEM_TM01, ITEM_HM01 = 289, 339

_MOVE_ID = {v: k for k, v in MOVE_NAMES.items()}

# item id -> (label "TM09"/"HM01", move name, move id)
TMHM: dict[int, tuple[str, str, int]] = {}
for _i, _m in enumerate(TM_MOVES):
    TMHM[ITEM_TM01 + _i] = (f"TM{_i + 1:02d}", _m, _MOVE_ID[_m])
for _i, _m in enumerate(HM_MOVES):
    TMHM[ITEM_HM01 + _i] = (f"HM{_i + 1:02d}", _m, _MOVE_ID[_m])

HM_MOVE_NAMES = frozenset(HM_MOVES)        # these can never be forgotten in the field


def resolve_tmhm(text: str) -> int | None:
    """'TM09', 'tm 9', 'HM01', 'Cut', 'bullet seed' -> item id, or None."""
    t = (text or "").strip().lower().replace(" ", "").replace("-", "")
    if not t:
        return None
    for iid, (label, move, _mid) in TMHM.items():
        if t in (label.lower(), move.lower().replace(" ", "")):
            return iid
    for prefix, base, count in (("tm", ITEM_TM01, 50), ("hm", ITEM_HM01, 8)):
        if t.startswith(prefix) and t[2:].isdigit() and 1 <= int(t[2:]) <= count:
            return base + int(t[2:]) - 1
    return None


def pick_forget(current: list[str], new_move: str, power: dict[str, int]) -> int | None:
    """Which of the 4 current moves to replace, as a 0-based index, or None if nothing is safe to
    lose. Never an HM move (the game refuses), never the last damaging move; prefers a status
    move (power 0), then the weakest damaging one — but not a move that is STRONGER than the new one."""
    cand = [(i, m) for i, m in enumerate(current) if m and m not in HM_MOVE_NAMES]
    if not cand:
        return None
    # HM moves (Cut, Strength, …) are utilities, not the attacks we're protecting.
    damaging = [i for i, m in enumerate(current) if m and m not in HM_MOVE_NAMES and power.get(m, 0) > 0]
    new_power = power.get(new_move, 0)

    def keep_score(item):
        i, m = item
        pw = power.get(m, 0)
        if pw == 0:
            return (0, 0)                       # status move: cheapest to lose
        if len(damaging) <= 1:
            return (3, pw)                      # the last attack — keep
        return (1, pw)                          # weakest attack goes first

    best = min(cand, key=keep_score)
    i, m = best
    if keep_score(best)[0] == 3:
        return None
    if power.get(m, 0) > max(new_power, 1) and new_power > 0 and keep_score(best)[0] == 1:
        return None                             # would trade a stronger attack for a weaker one
    return i
