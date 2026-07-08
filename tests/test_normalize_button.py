from agent.tools import normalize_button


def test_compass_words_map_to_dpad():
    assert normalize_button("North") == "Up"
    assert normalize_button("South") == "Down"
    assert normalize_button("East") == "Right"
    assert normalize_button("West") == "Left"


def test_compass_letters_map_to_dpad():
    assert normalize_button("N") == "Up"
    assert normalize_button("S") == "Down"
    assert normalize_button("E") == "Right"
    assert normalize_button("W") == "Left"


def test_case_insensitive_and_whitespace():
    assert normalize_button("west") == "Left"
    assert normalize_button("  Up  ") == "Up"
    assert normalize_button("start") == "Start"
    assert normalize_button("a") == "A"


def test_canonical_names_pass_through():
    for b in ("A", "B", "Select", "Start", "Up", "Down", "Left", "Right", "L", "R"):
        assert normalize_button(b) == b


def test_unknown_passes_through_for_backend_to_reject():
    # An unrecognised name is returned unchanged so the backend raises a clear
    # "invalid button" error rather than this silently swallowing a typo.
    assert normalize_button("Middle") == "Middle"
    assert normalize_button("") == ""
