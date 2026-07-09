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
    """Returns queued responses in order; each is a list of tool_calls (or None).
    Every response reports usage (prompt=10, completion=5) so spend tracking has
    something to accumulate."""
    def __init__(self, scripted):
        self._scripted = list(scripted)

    def create(self, **kwargs):
        tool_calls = self._scripted.pop(0) if self._scripted else None
        msg = types.SimpleNamespace(content="", tool_calls=tool_calls, model_extra={})
        choice = types.SimpleNamespace(message=msg)
        usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        return types.SimpleNamespace(choices=[choice], usage=usage)


def _make_client(scripted) -> AgentClient:
    client = AgentClient.__new__(AgentClient)   # bypass __init__ (no OpenAI/network)
    client.llm = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_FakeCompletions(scripted)))
    client.messages = [{"role": "system", "content": "sys"}]
    client._current_opponent = ""
    client.llm_calls = 0
    client.total_prompt_tokens = 0
    client.total_completion_tokens = 0
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


def test_usage_is_accumulated_across_calls(monkeypatch):
    # Round 1 (tool call) + round 2 (terminate) = 2 API calls → 2×(10+5) tokens.
    tc = _tool_call("call_1", "read_game_state", "{}")
    client = _make_client([[tc], None])
    monkeypatch.setattr(client, "_execute", lambda *a, **k: "state")

    client.step("obs")

    assert client.llm_calls == 2
    assert client.total_prompt_tokens == 20
    assert client.total_completion_tokens == 10
    assert client.total_tokens == 30


def test_step_survives_missing_usage(monkeypatch):
    # Some endpoints omit usage — step must not crash, call count still exact.
    client = _make_client([None])
    monkeypatch.setattr(_FakeCompletions, "create",
                        lambda self, **k: types.SimpleNamespace(
                            choices=[types.SimpleNamespace(
                                message=types.SimpleNamespace(
                                    content="", tool_calls=None, model_extra={}))]))
    client.step("obs")
    assert client.llm_calls == 1
    assert client.total_tokens == 0


# ── Save/load state must report truthfully to the model (#63) ─────────────────

class _FakeMgba:
    def __init__(self, save_ok=True, load_ok=True):
        self._save_ok, self._load_ok = save_ok, load_ok
    def save_state(self, slot=0):
        return self._save_ok
    def load_state(self, slot=0):
        return self._load_ok


def _client_with_mgba(mgba) -> AgentClient:
    client = AgentClient.__new__(AgentClient)
    client.mgba = mgba
    return client


def test_load_state_failure_is_reported_not_masked():
    client = _client_with_mgba(_FakeMgba(load_ok=False))
    msg = client._execute("load_state", '{"slot": 0}')
    assert "FAILED" in msg


def test_load_state_success_is_reported():
    client = _client_with_mgba(_FakeMgba(load_ok=True))
    msg = client._execute("load_state", '{"slot": 0}')
    assert "loaded" in msg.lower() and "FAILED" not in msg


def test_save_state_failure_is_reported():
    client = _client_with_mgba(_FakeMgba(save_ok=False))
    msg = client._execute("save_state", '{"slot": 2}')
    assert "FAILED" in msg and "2" in msg
