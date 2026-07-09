"""Pure tests for eval goals + scenario registry (no LLM/emulator → CI-safe)."""
import memory.long_term as lt
from game.state import GameState, GameContext
from evals import goals
from evals.scenarios import SCENARIOS, by_name


def _state(*, map_bank=3, map_id=0, party_count=1, x=5, y=5) -> GameState:
    return GameState(
        context=GameContext.OVERWORLD, badges=0, badge_bits=0,
        party=[], party_count=party_count, map_bank=map_bank, map_id=map_id,
        player_x=x, player_y=y, screen_fading=False,
    )


def _ltm(tmp_path, monkeypatch, **data):
    monkeypatch.setattr(lt, "PROGRESS_PATH", tmp_path / "p.json")
    m = lt.LongTermMemory()
    m.data.update(data)
    return m


def test_reached_map_true_and_false(tmp_path, monkeypatch):
    l = _ltm(tmp_path, monkeypatch)
    g = goals.reached_map(3, 2, "Pewter City")
    assert g.desc == "reach Pewter City"
    assert g(_state(map_bank=3, map_id=2), l) is True
    assert g(_state(map_bank=3, map_id=1), l) is False


def test_badges_at_least(tmp_path, monkeypatch):
    g = goals.badges_at_least(2)
    assert g(_state(), _ltm(tmp_path, monkeypatch, badges_earned=1)) is False
    assert g(_state(), _ltm(tmp_path, monkeypatch, badges_earned=2)) is True
    assert g(_state(), _ltm(tmp_path, monkeypatch, badges_earned=5)) is True


def test_has_milestone(tmp_path, monkeypatch):
    g = goals.has_milestone("got_cut")
    assert g(_state(), _ltm(tmp_path, monkeypatch, milestones=[])) is False
    assert g(_state(), _ltm(tmp_path, monkeypatch, milestones=["got_cut"])) is True


def test_party_size_at_least(tmp_path, monkeypatch):
    g = goals.party_size_at_least(2)
    assert g(_state(party_count=1), _ltm(tmp_path, monkeypatch)) is False
    assert g(_state(party_count=3), _ltm(tmp_path, monkeypatch)) is True


def test_all_of_and_any_of(tmp_path, monkeypatch):
    l = _ltm(tmp_path, monkeypatch, badges_earned=1)
    at_pewter = goals.reached_map(3, 2)
    has_badge = goals.badges_at_least(1)
    both = goals.all_of(at_pewter, has_badge)
    either = goals.any_of(at_pewter, has_badge)
    st_elsewhere = _state(map_bank=3, map_id=0)
    assert both(st_elsewhere, l) is False       # not at Pewter
    assert either(st_elsewhere, l) is True       # but has the badge
    assert "AND" in both.desc and "OR" in either.desc


def test_scenarios_registry_wellformed():
    assert SCENARIOS, "expected at least one scenario"
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names)), "scenario names must be unique"
    for s in SCENARIOS:
        assert s.max_steps > 0
        assert callable(s.goal) and s.goal.desc
    assert by_name("reach_pewter") is not None
    assert by_name("does_not_exist") is None


def test_pewter_scenario_marked_xfail_for_issue_59():
    # The Route 2 crossing is a known bug (#59); the scenario documents it so a
    # future fix shows up as an unexpected PASS rather than silent.
    assert by_name("reach_pewter").xfail == "#59"
