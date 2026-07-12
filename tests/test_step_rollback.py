"""A failed LLM call in step() must roll back the just-appended user turn, so retried
steps don't pile up dangling user messages (which the API rejects / that inflate token
cost). #69"""
import importlib.util

import pytest

requires_openai = pytest.mark.skipif(
    importlib.util.find_spec("openai") is None, reason="openai not installed")


class _Completions:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        raise self.exc


class _LLM:
    def __init__(self, exc):
        comp = _Completions(exc)
        self.chat = type("C", (), {"completions": comp})()
        self.completions = comp


def _client(exc):
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.messages = [{"role": "system", "content": "s"}]
    c.llm = _LLM(exc)
    c.llm_calls = 0
    c.total_prompt_tokens = 0
    c.total_completion_tokens = 0
    c._trim_image_history = lambda: None
    return c


@requires_openai
def test_failed_llm_call_rolls_back_the_user_turn():
    c = _client(RuntimeError("llm timeout"))
    before = list(c.messages)
    with pytest.raises(RuntimeError):
        c.step("look around")
    assert c.messages == before                 # user turn removed, nothing dangling


@requires_openai
def test_repeated_failures_do_not_accumulate_user_turns():
    c = _client(RuntimeError("llm timeout"))
    for _ in range(3):
        with pytest.raises(RuntimeError):
            c.step("look around")
    # exactly the original system message — no pile-up of unanswered user turns
    assert c.messages == [{"role": "system", "content": "s"}]
