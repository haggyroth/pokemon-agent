"""Conversation-history helpers (dependency-light so they're unit-testable).

Kept out of lm_studio_client.py so tests don't need the openai SDK.
"""


def trim_messages(messages: list[dict], max_history: int) -> list[dict]:
    """Trim history to ~max_history messages after the system prompt.

    The Chat Completions API requires every assistant `tool_calls` to be
    immediately followed by its matching `tool` responses. A naive tail slice
    can start on an orphaned `tool` message (its assistant was dropped) and get
    rejected with a 400. This cuts only at a `user` turn boundary, so a
    tool_calls/tool group is never split. If no safe boundary exists in range,
    the history is returned unchanged rather than corrupted.
    """
    if len(messages) <= max_history + 1:
        return messages
    system = messages[:1] if messages and messages[0].get("role") == "system" else []
    target = len(messages) - max_history
    for i in range(max(target, len(system)), len(messages)):
        if messages[i].get("role") == "user":
            return system + messages[i:]
    return messages
