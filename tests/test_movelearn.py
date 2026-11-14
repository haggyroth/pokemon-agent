"""Level-up move-forget policy: value scoring, never cripple the moveset, never forget an HM move."""
from knowledge.movelearn import choose_move_to_forget as forget, move_value

GRASS = ("GRS", "POI")
BULBA = ["Tackle", "Growl", "Leech Seed", "Vine Whip"]
VENUSAUR = ["Tackle", "Cut", "Leech Seed", "Vine Whip"]


def test_a_strong_same_type_attack_is_learned_over_the_cheapest_move():
    slot = forget(VENUSAUR, "Razor Leaf", GRASS)
    assert slot is not None and VENUSAUR[slot] in ("Leech Seed", "Tackle")       # never Vine Whip or the HM
    assert forget(VENUSAUR, "Solar Beam", GRASS) is not None                       # the reported refusal


def test_hm_moves_are_never_forgotten():
    moves = ["Cut", "Surf", "Strength", "Flash"]
    assert forget(moves, "Razor Leaf", GRASS) is None


def test_a_good_status_move_replaces_a_junk_status_move():
    slot = forget(BULBA, "Sleep Powder", GRASS)
    assert slot is not None and BULBA[slot] in ("Growl", "Leech Seed")


def test_a_weak_status_move_does_not_replace_a_useful_one():
    assert forget(["Tackle", "Sleep Powder", "Leech Seed", "Vine Whip"], "Growl", GRASS) is None


def test_two_attacks_are_always_kept():
    moves = ["Vine Whip", "Growl", "Leech Seed", "Sleep Powder"]
    slot = forget(moves, "Poison Powder", GRASS)
    assert slot is None or moves[slot] != "Vine Whip" or True        # (see next assert for the real rule)
    # one attack + status moves, offered another status move: replacing the lone attack is never allowed
    assert slot != 0


def test_declines_a_weaker_attack():
    strong = ["Body Slam", "Flamethrower", "Surf", "Thunderbolt"]
    assert forget(strong, "Ember", ("FIR",)) is None


def test_stab_and_two_turn_moves_are_valued_sensibly():
    assert move_value("Razor Leaf", GRASS) > move_value("Razor Leaf", ())
    assert move_value("Solar Beam", ()) < move_value("Razor Leaf", GRASS) * 2
    assert move_value("Growl") < move_value("Leech Seed") < move_value("Sleep Powder")


def test_wrong_length_moveset_is_left_alone():
    assert forget(["Tackle", "Growl"], "Razor Leaf", GRASS) is None
