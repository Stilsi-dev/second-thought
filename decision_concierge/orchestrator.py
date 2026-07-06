"""Coordinator agent — runs the perceive/plan/act/observe loop (Day 1) across
the skill library (Day 3), calling out to MCP tools (Day 2) and gating
sensitive output behind human confirmation (Day 4)."""

from . import mcp_client, security
from .config import CONFIDENCE_THRESHOLD, DOMAIN_SKILL, MAX_REANALYZE, get_client
from .skills import SkillRegistry

_registry = SkillRegistry()


def classify_domain(goal: str, client) -> str:
    text = goal.lower()
    med_kw = ("medication", "medicine", "supplement", "pill", "drug", "prescription",
              "vitamin", "dose", "should i take")
    meals_kw = ("eat", "meal", "food", "snack", "dish", "recipe", "cook", "drink",
                "breakfast", "lunch", "dinner", "diet")
    salary_kw = ("salary", "income", "paycheck", "payday", "budget my", "savings")
    if any(kw in text for kw in med_kw):
        return "medication"
    if any(kw in text for kw in meals_kw):
        return "meals"
    if any(kw in text for kw in salary_kw):
        return "salary"
    if client is None:
        return "purchase"

    from google.genai import types

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Classify this goal as exactly one word — 'purchase', 'salary', "
                f"'medication', or 'meals' (food/eating): {goal}"
            ),
            config=types.GenerateContentConfig(temperature=0),
        )
        label = resp.text.strip().lower()
        for d in ("medication", "meals", "salary", "purchase"):
            if d in label:
                return d
        return "purchase"
    except Exception:
        return "purchase"


def advance(session, user_reply: str | None = None) -> dict:
    """One turn of the agent loop. Returns a dict describing what the UI should
    show next: {"type": "question"|"confirm"|"report", ...}."""
    client = get_client()

    if session.domain is None:
        session.domain = classify_domain(session.goal, client)
        session.log(f"Coordinator: classified domain -> {session.domain}")
        security.audit("domain_classified", session.domain)

    if session.confidence < CONFIDENCE_THRESHOLD:
        session.log("Context Gathering skill: interviewing")
        instructions = _registry.instructions("context_gathering")
        result = _registry.run(
            "context_gathering", session, client, instructions, user_reply=user_reply
        )
        if not result["done"]:
            return {"type": "question", "question": result["question"], "confidence": result["confidence"]}
        session.log(f"Context Gathering skill: confidence {result['confidence']} reached")

    skill_name = DOMAIN_SKILL[session.domain]

    def _analyze():
        session.draft = _registry.run(
            skill_name,
            session,
            client,
            _registry.instructions(skill_name),
            mcp_call=mcp_client.call_tool,
        )
        session.draft_attempts += 1

    def _criticize():
        session.critique = _registry.run(
            "critic", session, client, _registry.instructions("critic")
        )

    if session.draft is None:
        session.log(f"{skill_name} skill: analyzing")
        _analyze()
        security.audit("draft_created", session.domain, session.facts)

    if session.critique is None:
        session.log("Critic skill: reviewing draft")
        _criticize()

    # Re-analyze loop: if the critic rejected the draft and we
    # still have retries, re-run the domain skill — it reads session.critique and
    # produces a corrected draft — then re-criticize. Capped by MAX_REANALYZE; a
    # still-failing draft ships flagged (critic_approved=False in the report)
    # rather than looping forever.
    while not session.critique["approved"] and session.draft_attempts <= MAX_REANALYZE:
        session.log(f"Critic rejected: {session.critique['issues']} -> Re-analyze")
        # Preserve the withdrawn draft + what caught it, so the Report can show
        # the before/after contrast — the self-correction IS the product.
        session.withdrawn.append(
            {
                "recommendation": session.draft.get("recommendation"),
                "caught_by": list(session.critique["issues"]),
            }
        )
        _analyze()
        _criticize()

    if security.is_sensitive(session.domain) and not session.confirmed:
        session.log("Security gate: human confirmation required (sensitive domain)")
        return {"type": "confirm", "draft": session.draft, "critique": session.critique}

    if session.report is None:
        session.log("Report skill: assembling final Decision Report")
        session.report = _registry.run("report", session)
        security.audit("report_finalized", session.domain, session.facts)

    return {"type": "report", "report": session.report}


def _apply_update(session, message: str, client) -> str | None:
    """Decide whether a post-report pushback carries a genuinely NEW fact (which
    legitimately changes the answer) versus mere pressure (which must not). This
    is the integrity of the challenge feature: it folds in *information*, never
    caves to *insistence*.

    Deterministic floor: a per-domain regex for the most common concrete update
    (a raised purchase budget). LLM ceiling: broader extraction across the
    domain's fields when a client is available. Default is to change nothing.
    """
    import re

    if session.domain == "purchase" and (re.search(r"budget|spend|afford|pay|cost", message, re.I) or "$" in message):
        m = re.search(r"[\d,]+(?:\.\d+)?\s*k?", message.lower())
        if m and any(ch.isdigit() for ch in m.group()):
            session.facts["budget"] = m.group().strip()
            return "budget"

    if client is None:
        return None

    from google.genai import types
    import json

    fields = [k for k, _ in _required_fields(session.domain)]
    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"The user already answered these fields: {session.facts}. "
                f"They now say: {message!r}. If (and only if) this states a NEW value "
                f"for one of these fields {fields}, return JSON {{field: new_value}}. "
                "If it is only pressure/insistence with no new fact, return {}."
            ),
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json"
            ),
        )
        update = json.loads(resp.text)
        for k, v in update.items():
            if k in fields and str(v).strip():
                session.facts[k] = str(v)
                return k
    except Exception:
        pass
    return None


def _required_fields(domain):
    from .skills.context_gathering.skill import REQUIRED_FIELDS

    return REQUIRED_FIELDS[domain]


def challenge(session, message: str) -> dict:
    """Handle a user pushing back on the finished report. If the pushback supplies
    a new fact, re-evaluate honestly; if it is only pressure, HOLD the ground and
    cite the fact the recommendation is anchored in. This is anti-sycophancy at
    its sharpest — the agent won't be talked out of the truth."""
    client = get_client()
    updated = _apply_update(session, message, client)

    if updated:
        session.log(f"Challenge: new fact provided ({updated}={session.facts[updated]!r}) -> re-evaluating")
        # Genuine new information: rebuild the decision from the domain step down.
        session.draft = None
        session.critique = None
        session.report = None
        session.withdrawn = []
        session.draft_attempts = 0
        session.confirmed = False  # sensitive domains must re-confirm after a change
        return advance(session)

    session.log("Challenge: pressure without new facts -> holding ground")
    anchor = (
        session.withdrawn[0]["caught_by"][0]
        if session.withdrawn
        else "the facts you gave me"
    )
    return {
        "type": "hold",
        "message": (
            "I hear you — but I'm not going to flip to a yes just because you'd "
            f"prefer one. This is anchored in what you told me: {anchor}. If "
            "something actually changed, tell me the new detail and I'll re-run."
        ),
        "report": session.report,
    }
