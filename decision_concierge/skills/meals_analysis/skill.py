from .. import _util

# Thresholds for the deterministic goal-alignment check. Illustrative, not
# clinical — they define "high" only relative to a goal the user stated.
SUGAR_LIMIT_G = 25
SODIUM_LIMIT_MG = 1000


def _goal_flags(goal: str, restrictions: str, nutrition: dict) -> list[str]:
    """Turn the stated goal + restrictions into concrete contradictions with the
    looked-up numbers. This is a NEW check shape vs the other domains: threshold-
    and-tag against a stated goal, not table equality."""
    g = f"{goal} {restrictions}".lower()
    issues = []

    sugar = nutrition.get("sugar_g")
    sodium = nutrition.get("sodium_mg")
    tags = set(nutrition.get("tags", []))
    allergens = set(nutrition.get("allergens", []))

    if any(w in g for w in ("sugar", "diabet", "blood sugar")) and sugar and sugar > SUGAR_LIMIT_G:
        issues.append(f"{sugar}g sugar exceeds your stated goal to cut sugar (>{SUGAR_LIMIT_G}g)")
    if any(w in g for w in ("sodium", "salt", "blood pressure", "hypertens")) and sodium and sodium > SODIUM_LIMIT_MG:
        issues.append(f"{sodium}mg sodium is high for your stated goal (>{SODIUM_LIMIT_MG}mg)")
    if ("vegetarian" in g or "vegan" in g) and tags and "vegetarian" not in tags and "vegan" not in tags:
        issues.append("Not vegetarian/vegan — conflicts with your stated diet")
    if "vegan" in g and "vegan" not in tags:
        issues.append("Not vegan — conflicts with your stated diet")

    def _tokens(s: str) -> list[str]:
        return [t.strip() for t in s.replace(";", ",").split(",") if t.strip() and t.strip() != "none"]

    for a in _tokens(restrictions.lower()):
        if any(a in al or al in a for al in allergens):
            issues.append(f"Contains a stated allergen/restriction: {a}")
    return issues


def check(session, draft) -> list[str]:
    """Deterministic contradiction floor. Fires in every mode: if the
    food conflicts with the user's stated goal/restrictions and the draft still
    waves it through, that's a self-contradiction. Conservative — only on a
    concrete lookup + stated goal."""
    nutrition = draft.get("_tool_data", {}).get("nutrition", {})
    rec = (draft.get("recommendation") or "").lower()
    steers_toward = not any(
        w in rec for w in ("reconsider", "swap", "avoid", "skip", "hold", "instead", "don't", "not ")
    )
    if not steers_toward:
        return []
    return _goal_flags(session.facts.get("goal", ""), session.facts.get("restrictions", ""), nutrition)


def run(session, client, instructions: str, mcp_call) -> dict:
    facts = session.facts
    nutrition = mcp_call("nutrition_lookup", {"item": facts.get("item", "")})
    flags = _goal_flags(facts.get("goal", ""), facts.get("restrictions", ""), nutrition)

    prior = session.critique.get("issues") if session.critique else None
    if prior:
        # Re-analyze: the first, agreeable take betrayed the stated goal. Withdraw
        # it and recommend a swap that fits.
        mock = {
            "recommendation": f"Reconsider — {facts.get('item', 'this')} conflicts with your stated goal; swap for something that fits",
            "reasoning": [f"On review: {issue}" for issue in prior],
            "risks": list(prior),
            "alternatives": ["Pick a lower-sugar/lower-sodium option, or one matching your diet"],
            "confidence": 0.7,
        }
    else:
        # First take is deliberately the agreeable "go ahead" — the sycophantic
        # answer the deterministic floor is here to catch when a goal is set.
        match = nutrition.get("match")
        mock = {
            "recommendation": f"Go ahead — {match or facts.get('item', 'that')} sounds like a fine choice.",
            "reasoning": [
                f"Looked up: {match or 'no match'}"
                + (f" ({nutrition.get('sugar_g')}g sugar, {nutrition.get('sodium_mg')}mg sodium)" if match else ""),
            ],
            "risks": [] if match else ["No nutrition match — couldn't check against your goal"],
            "alternatives": [],
            "confidence": 0.55,
        }

    critique_note = (
        f"\nA prior review flagged: {prior}. Produce a corrected recommendation that resolves those issues."
        if prior
        else ""
    )
    prompt = (
        f"User facts: {facts}\n"
        f"Nutrition lookup: {nutrition}\n"
        f"Deterministic goal conflicts: {flags}{critique_note}\n"
        "Return the JSON object described in your instructions. Compare only to the stated goal."
    )
    result = _util.generate_json(client, instructions, prompt, mock)
    result["_tool_data"] = {"nutrition": nutrition}
    return result
