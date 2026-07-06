def _value_line(session) -> str:
    """A one-line statement of the *benefit* to the user (Core Concept & Value),
    not the mechanism. Deterministic and honest: when the agent caught its own
    bad first take, that catch IS the value; otherwise the value is a
    fact-checked recommendation rather than an instant guess."""
    if session.withdrawn:
        caught = session.withdrawn[0]["caught_by"][0]
        return f"Caught its own first recommendation before you acted on it — {caught}."
    return "Reached a recommendation only after checking it against your own stated facts."


def run(session) -> dict:
    draft = session.draft or {}
    critique = session.critique or {}
    return {
        "value": _value_line(session),
        "domain": session.domain,
        "facts": dict(session.facts),
        "recommendation": draft.get("recommendation"),
        "reasoning": draft.get("reasoning", []),
        "risks": draft.get("risks", []) + critique.get("issues", []),
        "alternatives": draft.get("alternatives", []),
        "confidence": draft.get("confidence"),
        "critic_approved": critique.get("approved", True),
        "tool_data": draft.get("_tool_data", {}),
        "human_confirmed": session.confirmed,
        # The self-correction trail: each entry is a recommendation the agent
        # gave first and then withdrew, plus the stated fact that caught it.
        # Empty when the first draft passed — the contrast shows only when earned.
        "withdrawn": list(session.withdrawn),
    }
