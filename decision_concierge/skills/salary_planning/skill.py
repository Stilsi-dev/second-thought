from .. import _util


def check(session, draft) -> list[str]:
    """Deterministic contradiction floor. Fires in every mode.

    Rule: if the user stated outstanding debt but the plan steers money toward
    savings/a goal that isn't debt repayment, that's a contradiction with the
    user's own situation — grow savings while paying loan interest. Conservative:
    only fires when debt is clearly present and the goal isn't already about debt.
    """
    debt = _util.parse_amount(session.facts.get("debt", ""))
    goal = session.facts.get("goals", "").lower()
    rec = (draft.get("recommendation") or "").lower()
    goal_is_debt = any(w in goal for w in ("debt", "loan", "pay off", "payoff"))
    plan_grows_savings = "sav" in rec or "invest" in rec
    if debt > 0 and plan_grows_savings and not goal_is_debt and "debt" not in rec:
        return [f"Plan grows savings while ignoring stated debt of ~{debt:.0f}"]
    return []


def run(session, client, instructions: str, mcp_call) -> dict:
    facts = session.facts
    income = _util.parse_amount(facts.get("monthly_income", ""))
    fixed = _util.parse_amount(facts.get("fixed_expenses", ""))
    debt = _util.parse_amount(facts.get("debt", ""))
    savings = _util.parse_amount(facts.get("existing_savings", ""))

    allocation = mcp_call(
        "budget_allocator", {"monthly_income": income, "fixed_expenses": fixed}
    )

    risks = []
    if debt > 0:
        risks.append(f"Existing debt of ~{debt:.0f} should be prioritized before discretionary spend")
    if allocation.get("remaining_after_fixed", 0) < income * 0.2:
        risks.append("Fixed expenses consume most of income — thin savings margin")

    # Re-analyze pass: prior critique => first plan was rejected.
    # Redirect the surplus to debt so the corrected plan resolves the conflict.
    prior = session.critique.get("issues") if session.critique else None
    if prior:
        mock = {
            "recommendation": f"Direct the ~{allocation.get('savings_target')} surplus to debt payoff first, then resume saving",
            "reasoning": [f"On review: {issue}" for issue in prior]
            + [f"Debt {debt:.0f} outranks new savings while interest accrues"],
            "risks": ["Initial savings-first plan was withdrawn after self-review"],
            "alternatives": ["Split the surplus 70/30 debt/savings if the debt is low-interest"],
            "confidence": 0.7,
        }
    else:
        mock = {
            "recommendation": f"Allocate savings target ~{allocation.get('savings_target')} toward: {facts.get('goals', 'your goal')}",
            "reasoning": [
                f"Income {income:.0f} minus fixed expenses {fixed:.0f} leaves {allocation.get('remaining_after_fixed')}",
                f"Existing savings: {savings:.0f}",
            ],
            "risks": risks,
            "alternatives": [],
            "confidence": 0.6,
        }

    critique_note = (
        f"\nA prior review flagged: {prior}. Produce a corrected plan that resolves those issues."
        if prior
        else ""
    )
    prompt = (
        f"User facts: {facts}\n"
        f"Computed allocation: {allocation}{critique_note}\n"
        "Return the JSON object described in your instructions."
    )
    result = _util.generate_json(client, instructions, prompt, mock)
    result["_tool_data"] = {"allocation": allocation}
    return result
