from .. import _util


def check(session, draft) -> list[str]:
    """Deterministic contradiction floor: catch a draft that
    conflicts with the user's own stated facts, without needing an LLM. Fires
    in every mode. Conservative on purpose — only high-confidence conflicts, so
    a false 'you contradicted yourself' never erodes trust.

    Rule: if we know both the stated budget and the recommended item's catalog
    price, and the price exceeds budget while the draft still recommends buying,
    that's a self-contradiction.
    """
    budget = _util.parse_amount(session.facts.get("budget", ""))
    price = (draft.get("_tool_data", {}).get("catalog") or {}).get("price")
    rec = (draft.get("recommendation") or "").lower()
    recommends_buy = not any(w in rec for w in ("reconsider", "wait", "hold", "don't"))
    if budget and price and price > budget and recommends_buy:
        return [f"Recommends an item at {price:.0f}, over the stated budget of {budget:.0f}"]
    return []


def run(session, client, instructions: str, mcp_call) -> dict:
    facts = session.facts
    budget = _util.parse_amount(facts.get("budget", ""))

    catalog = mcp_call("product_price_lookup", {"item": facts.get("item", "")})
    price = catalog.get("price")

    fit = None
    if price and budget:
        fit = mcp_call(
            "affordability_calculator", {"monthly_income": budget, "price": price}
        )

    # Re-analyze pass: a prior critique means the first draft was
    # rejected. Back off to a "reconsider" recommendation that resolves the
    # conflict — this is the self-correction the anti-sycophancy pitch shows off,
    # and it lands deterministically even offline.
    prior = session.critique.get("issues") if session.critique else None
    if prior:
        mock = {
            "recommendation": "Reconsider — the initial pick conflicts with your constraints",
            "reasoning": [f"On review: {issue}" for issue in prior]
            + [f"Stated budget ~{budget:.0f} vs price {price if price else 'unknown'}"],
            "risks": ["First recommendation was withdrawn after self-review"],
            "alternatives": ["Raise the budget, or pick a cheaper option in the same category"],
            "confidence": 0.7,
        }
    else:
        mock = {
            "recommendation": catalog.get("match") or facts.get("item", "the item"),
            "reasoning": [
                f"Matched catalog entry: {catalog.get('match') or 'no exact match'}",
                f"Stated budget ~{budget:.0f} vs price {price if price else 'unknown'}",
            ],
            "risks": (
                ["No catalog match — price/rating unverified"] if not catalog.get("match") else []
            ),
            "alternatives": [],
            "confidence": 0.6,
        }

    critique_note = (
        f"\nA prior review flagged: {prior}. Produce a corrected recommendation "
        "that resolves those issues."
        if prior
        else ""
    )
    prompt = (
        f"User facts: {facts}\n"
        f"Catalog lookup: {catalog}\n"
        f"Budget-fit: {fit}{critique_note}\n"
        "Return the JSON object described in your instructions."
    )
    result = _util.generate_json(client, instructions, prompt, mock)
    result["_tool_data"] = {"catalog": catalog, "budget_fit": fit}
    return result
