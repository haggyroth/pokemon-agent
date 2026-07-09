"""EpisodeResult scorecard shape (imports main → needs openai; skips in CI)."""
import pytest

pytest.importorskip("openai")

import main  # noqa: E402


def _result(**kw):
    base = dict(reason="goal", passed=True, steps=12, reward=3.5,
                llm_calls=40, prompt_tokens=1000, completion_tokens=200,
                final_map=(3, 2), final_pos=(5, 6), badges=1,
                milestones=["starter_chosen"], stuck_ratio=0.25, goal_desc="reach Pewter")
    base.update(kw)
    return main.EpisodeResult(**base)


def test_total_tokens_sums_prompt_and_completion():
    assert _result().total_tokens == 1200


def test_summary_contains_key_fields():
    s = _result().summary()
    assert "PASS" in s and "steps=12" in s and "reward=3.5" in s and "stuck=25%" in s


def test_summary_marks_failure():
    assert "----" in _result(passed=False).summary()


def test_to_dict_roundtrips_and_includes_total_tokens():
    d = _result().to_dict()
    assert d["reason"] == "goal" and d["final_map"] == (3, 2)
    assert d["total_tokens"] == 1200
    assert d["milestones"] == ["starter_chosen"]
