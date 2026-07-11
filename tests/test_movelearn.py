"""Level-up move-forget policy: never drop the last damage move; don't stack status."""
from knowledge.movelearn import choose_move_to_forget as forget

BULBA = ["Tackle", "Growl", "Leech Seed", "Vine Whip"]   # 2 damage, 2 non-damage


def test_declines_status_move_when_already_has_one():
    # The reported bug: Sleep/Poison Powder overwrote Tackle. Must DECLINE now.
    assert forget(BULBA, "Poison Powder") is None
    assert forget(BULBA, "Sleep Powder") is None


def test_damage_move_forgets_a_status_slot_keeping_all_damage():
    slot = forget(BULBA, "Razor Leaf")
    assert slot == 1                     # Growl (first non-damaging slot)
    assert BULBA[slot] not in ("Tackle", "Vine Whip")   # never a damage move


def test_status_move_over_all_damage_forgets_weakest_keeping_two():
    # Four damaging moves, offered a status move → replace the weakest, keep >=2 dmg.
    moves = ["Tackle", "Scratch", "Ember", "Water Gun"]   # all damaging
    slot = forget(moves, "Sleep Powder")
    assert slot is not None and slot in range(4)


def test_declines_weaker_damage_move():
    strong = ["Body Slam", "Flamethrower", "Surf", "Thunderbolt"]
    assert forget(strong, "Ember") is None            # Ember weaker than all


def test_learns_stronger_damage_move_over_weakest():
    moves = ["Tackle", "Ember", "Water Gun", "Vine Whip"]  # Tackle weakest (35)
    slot = forget(moves, "Flamethrower")               # 95 power, upgrade
    assert slot == 0


def test_never_returns_only_damage_slot():
    # One damage move + three status: a damaging new move forgets a status slot,
    # never the lone damage move.
    moves = ["Vine Whip", "Growl", "Leech Seed", "Sleep Powder"]
    slot = forget(moves, "Razor Leaf")
    assert moves[slot] != "Vine Whip"
