"""Context Gathering skill — the adaptive interview loop (Day 1 agent loop +
Day 3 skill). Deterministic checklist drives *what* is asked (so confidence is
always accurate and the demo never stalls); the LLM only rephrases *how* it's
asked, when a client is available.
"""

from ...config import GEMINI_MODEL, MAX_DEEPENING_PROBES
from .. import _util

REQUIRED_FIELDS = {
    "purchase": [
        ("item", "What are you thinking of buying?"),
        ("budget", "What's your budget for this?"),
        ("primary_use", "What will you mainly use it for?"),
        ("must_haves", "Any must-have features or dealbreakers?"),
        ("timeline", "How soon do you need it?"),
    ],
    "salary": [
        ("monthly_income", "What's your monthly take-home income?"),
        ("fixed_expenses", "What are your fixed monthly expenses (rent, bills, etc.)?"),
        ("existing_savings", "How much do you currently have in savings?"),
        ("debt", "Do you have any outstanding debt? If so, how much?"),
        ("goals", "What's your top financial goal right now?"),
    ],
    "medication": [
        ("new_item", "What medication or supplement is being considered (for you or someone you care for)?"),
        ("current_meds", "What medications or supplements are currently taken? (comma-separated)"),
        ("allergies", "Any known drug allergies? (comma-separated, or 'none')"),
        ("reason", "What is this new item hoping to help with?"),
    ],
    "meals": [
        ("item", "What food or dish are you about to eat or serve?"),
        ("goal", "What health goal should this fit? (e.g. lower sugar, low sodium, vegetarian — or 'none')"),
        ("restrictions", "Any allergies or hard dietary restrictions in the household? (comma-separated, or 'none')"),
        ("context", "Who's it for and what's the occasion? (e.g. quick lunch for the kids)"),
    ],
}


def _rephrase(question: str, session, client, instructions: str) -> str:
    if client is None:
        return question

    from google.genai import types

    prompt = (
        f"Facts collected so far: {session.facts}\n"
        f"Next required question (rephrase naturally, one sentence): {question}"
    )
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=instructions),
        )
        return resp.text.strip() or question
    except Exception:
        return question


def _deepen(session, client, instructions: str) -> dict:
    """Ceiling: once the floor is met and a client exists, let the LLM decide
    whether the collected context is deep enough. If not, it emits ONE extra
    'deepening' probe (capped by MAX_DEEPENING_PROBES). Deepening probes sharpen
    understanding but never move the confidence bar, which tracks only the floor.
    Falls back to sufficient=True on any error so the loop always terminates."""
    prompt = (
        f"Domain: {session.domain}. Facts collected: {session.facts}\n"
        "The required checklist is complete. Is anything decision-critical still "
        "ambiguous or missing? Respond as JSON: "
        '{"sufficient": bool, "question": "<one short follow-up if not sufficient>"}'
    )
    return _util.generate_json(client, instructions, prompt, mock={"sufficient": True})


def run(session, client, instructions: str, user_reply: str | None = None) -> dict:
    fields = REQUIRED_FIELDS[session.domain]

    if user_reply is not None and session.pending_field:
        session.facts[session.pending_field] = user_reply.strip()
        session.pending_field = None

    missing = [key for key, _ in fields if key not in session.facts]
    session.confidence = round((len(fields) - len(missing)) / len(fields), 2)

    # Floor: always ask for the next required field first (drives MOCK_MODE).
    if missing:
        next_key, base_question = next((k, q) for k, q in fields if k == missing[0])
        session.pending_field = next_key
        question = _rephrase(base_question, session, client, instructions)
        return {"done": False, "question": question, "confidence": session.confidence}

    # Ceiling: floor complete. Deepen only if a client exists and we haven't
    # hit the probe cap or already judged the context sufficient.
    if client is not None and not session.sufficient and session.probe_count < MAX_DEEPENING_PROBES:
        verdict = _deepen(session, client, instructions)
        if not verdict.get("sufficient", True) and verdict.get("question"):
            session.probe_count += 1
            session.pending_field = f"probe_{session.probe_count}"
            session.log(f"Context Gathering skill: deepening +{session.probe_count}")
            return {"done": False, "question": verdict["question"], "confidence": session.confidence}
        session.sufficient = True

    return {"done": True, "confidence": session.confidence}
