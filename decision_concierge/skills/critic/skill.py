import importlib

from .. import _util
from ...config import DOMAIN_SKILL


def _domain_check(session) -> list[str]:
    """Call the active domain skill's deterministic contradiction check (the
    floor). Domain-owned so the critic core never changes per domain.
    A domain skill without a check() simply contributes no floor issues."""
    module = importlib.import_module(
        f"decision_concierge.skills.{DOMAIN_SKILL[session.domain]}.skill"
    )
    check = getattr(module, "check", None)
    return check(session, session.draft) if check else []


def run(session, client, instructions: str) -> dict:
    # Floor: deterministic, always runs (offline too). This is what makes the
    # "argues with its own recommendation" behavior fire without an API key.
    floor_issues = _domain_check(session)

    # Ceiling: LLM catches subtler contradictions. In MOCK_MODE generate_json
    # returns the mock unchanged, so the floor alone decides approval offline.
    mock = {"issues": floor_issues, "approved": not floor_issues}
    prompt = (
        f"User facts: {session.facts}\n"
        f"Draft recommendation: {session.draft}\n"
        f"Deterministic checks already found: {floor_issues}\n"
        "Add any FURTHER contradictions with the user's stated facts (do not repeat "
        "the ones above). Return the JSON object described in your instructions."
    )
    ceiling = _util.generate_json(client, instructions, prompt, mock)

    issues = list(dict.fromkeys(floor_issues + ceiling.get("issues", [])))
    return {"issues": issues, "approved": not issues}
