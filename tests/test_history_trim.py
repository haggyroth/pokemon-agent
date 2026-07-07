"""History trimming never splits a tool_calls/tool-response group (#16)."""
from agent.history import trim_messages


def _roles(msgs):
    return [m["role"] for m in msgs]


def test_short_history_unchanged():
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "u"}]
    assert trim_messages(msgs, 20) is msgs


def test_keeps_system_and_cuts_at_user_boundary():
    # system + 8 alternating turns; trim to last 3 messages.
    msgs = [{"role": "system", "content": "s"}]
    for i in range(4):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    out = trim_messages(msgs, 3)
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "user"          # starts on a turn boundary
    assert len(out) < len(msgs)


def test_never_starts_on_orphaned_tool_message():
    # A tool group: user -> assistant(tool_calls) -> tool -> assistant.
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "r"},
        {"role": "assistant", "content": "a0"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
    ]
    # max_history small enough that a naive tail slice would begin mid-group.
    out = trim_messages(msgs, 3)
    assert out[0]["role"] == "system"
    # first non-system message must be a user turn, never a tool/orphan
    assert out[1]["role"] == "user"
    assert "tool" not in _roles(out[1:2])


def test_no_user_boundary_returns_unchanged():
    # Degenerate: a long single turn with no later user message -> keep as-is
    # rather than corrupt the tool pairing.
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "r"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "2"}]},
            {"role": "tool", "tool_call_id": "2", "content": "r"}]
    out = trim_messages(msgs, 2)
    assert out is msgs  # no safe cut point
