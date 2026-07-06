from .. import _util

DISCLAIMER = "Not medical advice — confirm with a pharmacist or physician."


def check(session, draft) -> list[str]:
    """Deterministic contradiction floor. Fires in every mode.

    The strongest catch in the whole system: if the interaction tool flagged the
    candidate against the user's OWN stated allergy or current medication, and
    the draft still steers them toward starting it, that's a self-contradiction
    with real stakes. Conservative — only fires on a concrete tool hit.
    """
    tool = draft.get("_tool_data", {}).get("interaction", {})
    rec = (draft.get("recommendation") or "").lower()
    # "recommends starting" unless it clearly defers/holds/warns.
    steers_toward = not any(
        w in rec for w in ("do not", "don't", "avoid", "hold off", "check with", "consult", "reconsider")
    )
    issues = []
    if tool.get("allergy_hit") and steers_toward:
        issues.append(f"Candidate matches a stated allergy: {tool['allergy_hit']}")
    if tool.get("interactions") and steers_toward:
        issues.append(
            f"Candidate interacts with current medication: {', '.join(tool['interactions'])}"
        )
    return issues


def run(session, client, instructions: str, mcp_call) -> dict:
    facts = session.facts
    interaction = mcp_call(
        "drug_interaction_lookup",
        {
            "item": facts.get("new_item", ""),
            "current_meds": facts.get("current_meds", ""),
            "allergies": facts.get("allergies", ""),
        },
    )
    allergy_hit = interaction.get("allergy_hit")
    interactions = interaction.get("interactions", [])

    prior = session.critique.get("issues") if session.critique else None
    if prior:
        # Re-analyze: the first take glossed over a conflict. Withdraw it and
        # defer firmly to a professional.
        mock = {
            "recommendation": f"Do not start {facts.get('new_item', 'this')} without checking with your pharmacist — a conflict was found. {DISCLAIMER}",
            "reasoning": [f"On review: {issue}" for issue in prior],
            "risks": [f"{allergy_hit or ', '.join(interactions)}"],
            "alternatives": ["Ask your pharmacist for a safer alternative given your current meds"],
            "confidence": 0.7,
        }
    elif allergy_hit or interactions:
        flags = []
        if allergy_hit:
            flags.append(f"allergy match: {allergy_hit}")
        if interactions:
            flags.append(f"interacts with: {', '.join(interactions)}")
        mock = {
            "recommendation": f"Bring these flags to your pharmacist before starting {facts.get('new_item', 'this')}. {DISCLAIMER}",
            "reasoning": [f"Interaction check found: {'; '.join(flags)}"],
            "risks": flags,
            "alternatives": [],
            "confidence": 0.6,
        }
    else:
        mock = {
            "recommendation": f"No conflict found in your stated meds/allergies, but confirm with a pharmacist before starting {facts.get('new_item', 'this')}. {DISCLAIMER}",
            "reasoning": ["No allergy or interaction found in the checked list (not a safety guarantee)"],
            "risks": ["Checked against a limited list only"],
            "alternatives": [],
            "confidence": 0.5,
        }

    critique_note = (
        f"\nA prior review flagged: {prior}. Produce a corrected recommendation that resolves those issues."
        if prior
        else ""
    )
    prompt = (
        f"User facts: {facts}\n"
        f"Interaction lookup: {interaction}{critique_note}\n"
        "Return the JSON object described in your instructions. Never assert the drug is safe."
    )
    result = _util.generate_json(client, instructions, prompt, mock)
    result["_tool_data"] = {"interaction": interaction}
    return result
