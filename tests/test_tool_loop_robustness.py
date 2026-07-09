"""Tool-execution loop must never orphan tool_calls in history (#61).

The assistant message carrying `tool_calls` is appended to history before tools
run. If a tool raises (malformed/truncated args) and we bail, that message is
left without its matching `role:"tool"` responses, and every subsequent Chat
Completions request 400s. This locks in: a raising _execute still yields exactly
one tool response per tool_call, and malformed JSON args don't crash the loop.

Needs the openai SDK (AgentClient imports it); skipped in the dependency-light
CI job, same as the binding/ROM tests.
"""
import types
import pytest

pytest.importorskip("openai")

from agent.lm_studio_client import AgentClient  # noqa: E402


# ── Minimal fakes ─────────────────────────────────────────────────────────────

def _tool_call(call_id: str, name: str, arguments: str):
    fn = types.SimpleNamespace(name=name, arguments=arguments)
    return types.SimpleNamespace(
        id=call_id, function=fn,
        model_dump=lambda: {"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": arguments}},
    )


class _FakeCompletions:
    """Returns queued responses in order; each is a list of tool_calls (or None)."""
    def __init__(self, scripted):
        self._scripted = list(scripted)

    def create(self, **kwargs):
        tool_calls = self._scripted.pop(0) if self._scripted else None
        msg = types.SimpleNamespace(content="", tool_calls=tool_calls, model_extra={})
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])


def _make_client(scripted) -> AgentClient:
    client = AgentClient.__new__(AgentClient)   # bypass __init__ (no OpenAI/network)
    client.llm = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_FakeCompletions(scripted)))
    client.messages = [{"role": "system", "content": "sys"}]
    client._current_opponent = ""
    return client


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_raising_execute_still_appends_one_tool_response(monkeypatch):
    # Round 1: one tool call that will blow up. Round 2: no tool calls (terminate).
    tc = _tool_call("call_1", "walk_to", '{"x": 5, "y": 3}')
    client = _make_client([[tc], None])
    monkeypatch.setattr(client, "_execute",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    reasoning, actions = client.step("obs")

    tool_msgs = [m for m in client.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_1"
    assert "failed" in tool_msgs[0]["content"].lower()
    # And the assistant tool_calls message that preceded it is present (not orphaned).
    assert any(m["role"] == "assistant" and m.get("tool_calls") for m in client.messages)


def test_malformed_json_args_do_not_crash_action_logging(monkeypatch):
    # Truncated JSON in a press_button call — _execute succeeds (fake), but the
    # action-logging json.loads must not raise on the bad args.
    tc = _tool_call("call_2", "press_button", '{"button": "A"')  # missing closing brace
    client = _make_client([[tc], None])
    monkeypatch.setattr(client, "_execute", lambda *a, **k: "ok")

    reasoning, actions = client.step("obs")   # must not raise

    tool_msgs = [m for m in client.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    # press_button action is still recorded (button unknown → '?')
    assert actions == ["press:?"]


def test_every_tool_call_gets_a_response(monkeypatch):
    # Two tool calls in one round, the first raises — BOTH must get a response so
    # the tool_calls group is complete.
    tcs = [_tool_call("a", "walk_to", "{}"), _tool_call("b", "read_game_state", "{}")]
    client = _make_client([tcs, None])

    def flaky(name, _args):
        if name == "walk_to":
            raise ValueError("nope")
        return "state"
    monkeypatch.setattr(client, "_execute", flaky)

    client.step("obs")

    ids = [m["tool_call_id"] for m in client.messages if m["role"] == "tool"]
    assert ids == ["a", "b"]
