"""History trimming never splits a tool_calls/tool-response group (#16)."""
from agent.history import trim_messages, strip_control_tokens


def test_strip_control_tokens():
    assert strip_control_tokens("hello") == "hello"
    assert strip_control_tokens("<|channel|>analysis<|message|>hi") == "analysishi"
    assert strip_control_tokens("go <|channel>north") == "go north"  # malformed form
    assert strip_control_tokens("") == ""
    assert strip_control_tokens("press <|end|>") == "press "


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


def test_no_boundary_single_turn_keeps_last_user_group(msgs=None):
    # Only one user turn (right after system) with a long tool group after it: the
    # last user group IS the whole history, so hard-reset returns the same content
    # (can't trim below one turn) — but never oversized or corrupted.
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "r"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "2"}]},
            {"role": "tool", "tool_call_id": "2", "content": "r"}]
    out = trim_messages(msgs, 2)
    assert out == msgs and out[1]["role"] == "user"      # valid, starts on the user turn


def test_no_boundary_in_window_hard_resets_to_last_user_group():
    # Last user turn is BEFORE the trim window, followed by a long tool-only stretch.
    # Rather than return oversized history, hard-reset to system + that last user group,
    # dropping the earlier turns (#69).
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "u0"},
            {"role": "assistant", "content": "a0"},
            {"role": "user", "content": "u1"}]
    for i in range(3):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": str(i)}]})
        msgs.append({"role": "tool", "tool_call_id": str(i), "content": "r"})
    out = trim_messages(msgs, 3)
    assert out[0]["role"] == "system"
    assert out[1] == {"role": "user", "content": "u1"}   # dropped u0/a0, kept last group
    assert len(out) < len(msgs)
    # every tool message still has its assistant(tool_calls) immediately before it
    for i, m in enumerate(out):
        if m["role"] == "tool":
            assert out[i - 1]["role"] == "assistant" and "tool_calls" in out[i - 1]
