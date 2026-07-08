"""Best-move suggestion excludes status moves and applies STAB (#19)."""
from knowledge.battle import battle_summary


def test_status_move_not_suggested_as_best():
    # Growl (status) vs Tackle (Normal, damaging) against a Rattata (Normal).
    # Neither is super-effective, but the damaging move must be picked, not Growl.
    out = battle_summary(["Tackle", "Growl"], "RATTATA", 1.0, pp_list=[35, 40])
    assert "Best move: Tackle" in out
    assert "Best move: Growl" not in out


def test_super_effective_damaging_move_wins():
    # Vine Whip (Grass) is 2x vs Geodude (Rock/Ground); Growl is status.
    out = battle_summary(["Growl", "Vine Whip"], "GEODUDE", 1.0, pp_list=[40, 25])
    assert "Best move: Vine Whip" in out
    assert "super effective" in out


def test_stab_breaks_tie_toward_same_type():
    # Both neutral (x1) vs Pidgey; Ember is STAB for a Fire attacker, Tackle isn't.
    out = battle_summary(["Tackle", "Ember"], "PIDGEY", 1.0, pp_list=[35, 25],
                         attacker_types=("FIR",))
    assert "Best move: Ember" in out


def test_strong_neutral_beats_weak_super_effective():
    # Powder Snow (Ice, 40) is 2x on Pidgey (Normal/Flying) -> ~80 expected.
    # Return (Normal, 102) is neutral -> 102. Power-aware ranking picks Return.
    out = battle_summary(["Powder Snow", "Return"], "PIDGEY", 1.0, pp_list=[25, 20])
    assert "Best move: Return" in out
    assert "no super effective option" in out


def test_strong_super_effective_still_wins():
    # A high-power super-effective move should of course still be picked.
    out = battle_summary(["Powder Snow", "Blizzard"], "PIDGEY", 1.0, pp_list=[25, 5])
    assert "Best move: Blizzard" in out
    assert "super effective" in out


def test_all_status_moves_gives_no_best_move():
    out = battle_summary(["Growl", "Tail Whip"], "RATTATA", 1.0, pp_list=[40, 30])
    assert "Best move:" not in out


def test_low_hp_warning_still_present():
    out = battle_summary(["Tackle"], "RATTATA", 0.2, pp_list=[35])
    assert "consider healing" in out
