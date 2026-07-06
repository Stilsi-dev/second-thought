"""Smoke tests: full agent loop end-to-end, offline (no API key needed), for
both domains, including the human-confirmation gate and the deterministic
self-correction loop.

An autouse fixture forces MOCK_MODE (get_client -> None) so results are
deterministic regardless of whether the developer has a key in their .env.
The dynamic LLM ceiling is exercised separately with a real key, not here.

Run with: python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decision_concierge import orchestrator
from decision_concierge.memory import Session
from decision_concierge.orchestrator import advance, challenge


@pytest.fixture(autouse=True)
def force_offline(monkeypatch):
    """Pin every test to the deterministic no-client path."""
    monkeypatch.setattr(orchestrator, "get_client", lambda: None)


def _drive(session, answers):
    turn = advance(session)
    for answer in answers:
        assert turn["type"] == "question", turn
        turn = advance(session, user_reply=answer)
    return turn


def test_purchase_flow_reaches_report():
    session = Session(goal="I'm thinking about buying a MacBook Air M4")
    turn = _drive(
        session,
        answers=["MacBook Air M4", "$1200", "coding and school", "long battery life", "this month"],
    )
    assert turn["type"] == "report"
    report = turn["report"]
    assert report["domain"] == "purchase"
    assert report["recommendation"]
    assert "facts" in report


def test_salary_flow_requires_human_confirmation():
    session = Session(goal="I just got my salary, help me budget it")
    turn = _drive(
        session,
        answers=["35000", "14000", "5000", "0", "build an emergency fund"],
    )
    assert turn["type"] == "confirm"

    turn = advance(session)
    assert turn["type"] == "confirm", "must stay gated until explicitly confirmed"

    session.confirmed = True
    turn = advance(session)
    assert turn["type"] == "report"
    assert turn["report"]["human_confirmed"] is True


def test_purchase_over_budget_self_corrects_offline():
    """The anti-sycophancy hero moment, offline: the deterministic critic floor
    catches a recommendation priced over the stated budget, and one Re-analyze
    produces a corrected 'reconsider' draft that passes."""
    session = Session(goal="I want to buy a MacBook Pro")
    turn = _drive(
        session,
        answers=["MacBook Pro", "$1000", "everyday use", "none", "no rush"],
    )
    assert turn["type"] == "report"
    report = turn["report"]
    assert session.draft_attempts == 2, "critic rejection should trigger exactly one Re-analyze"
    assert report["critic_approved"] is True, "corrected draft should pass the floor"
    assert "reconsider" in report["recommendation"].lower()
    # The before/after contrast must be captured for the UI.
    assert len(report["withdrawn"]) == 1
    assert "budget" in report["withdrawn"][0]["caught_by"][0].lower()


def test_clean_flow_has_no_withdrawn_contrast():
    """When the first draft passes, there's no correction to show."""
    session = Session(goal="I'm thinking about buying a MacBook Air M4")
    turn = _drive(
        session,
        answers=["MacBook Air M4", "$1200", "coding", "none", "this month"],
    )
    assert turn["type"] == "report"
    assert turn["report"]["withdrawn"] == []


def test_salary_debt_contradiction_self_corrects():
    """Salary floor: a plan that grows savings while ignoring stated debt is a
    contradiction; Re-analyze redirects the surplus to debt payoff."""
    session = Session(goal="help me budget my paycheck")
    turn = _drive(
        session,
        answers=["40000", "15000", "2000", "20000", "buy a laptop"],
    )
    assert turn["type"] == "confirm"
    session.confirmed = True
    turn = advance(session)

    assert turn["type"] == "report"
    assert session.draft_attempts == 2
    assert turn["report"]["critic_approved"] is True
    assert "debt" in turn["report"]["recommendation"].lower()


def test_medication_allergy_self_corrects_and_gates():
    """Highest-stakes catch: a candidate that hits the user's stated allergy is
    flagged deterministically, one Re-analyze withdraws it, and — because
    medication is a sensitive domain — the report waits on human confirmation."""
    session = Session(goal="should I take aspirin for my headache")
    turn = _drive(
        session,
        answers=["aspirin", "none", "aspirin", "headaches"],
    )
    assert session.domain == "medication"
    assert turn["type"] == "confirm", "medication is sensitive -> human gate"

    session.confirmed = True
    turn = advance(session)
    assert turn["type"] == "report"
    report = turn["report"]
    assert session.draft_attempts == 2
    assert report["critic_approved"] is True
    assert report["withdrawn"], "the withdrawn first take must be captured"
    assert "allergy" in report["withdrawn"][0]["caught_by"][0].lower()
    assert "do not" in report["recommendation"].lower()


def test_medication_facts_redacted_in_audit(tmp_path, monkeypatch):
    """Health PII (meds/allergies) must be redacted before the audit log."""
    from decision_concierge import security

    monkeypatch.setattr(security, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
    redacted = security.redact({"current_meds": "warfarin", "reason": "pain"})
    assert redacted["current_meds"] == "<redacted>"
    assert redacted["reason"] == "pain"


def test_meals_goal_conflict_self_corrects_and_gates():
    """The everyday case: an agreeable 'go ahead' that betrays the user's own
    stated health goal is caught deterministically, withdrawn via one Re-analyze,
    and gated (meals is sensitive household-health data)."""
    session = Session(goal="what should I eat, thinking a smoothie")
    turn = _drive(
        session,
        answers=["smoothie", "lower blood sugar", "none", "quick breakfast"],
    )
    assert session.domain == "meals"
    assert turn["type"] == "confirm", "meals is sensitive -> human gate"

    session.confirmed = True
    turn = advance(session)
    assert turn["type"] == "report"
    report = turn["report"]
    assert session.draft_attempts == 2
    assert report["critic_approved"] is True
    assert report["withdrawn"], "the agreeable first take must be captured"
    assert "sugar" in report["withdrawn"][0]["caught_by"][0].lower()
    assert "reconsider" in report["recommendation"].lower()


def test_meals_no_goal_conflict_passes_clean():
    """A choice that fits the stated goal should NOT be second-guessed."""
    session = Session(goal="what should I eat for lunch")
    turn = _drive(
        session,
        answers=["green salad", "lower blood sugar", "none", "quick lunch"],
    )
    assert turn["type"] == "confirm"
    session.confirmed = True
    turn = advance(session)
    assert turn["type"] == "report"
    assert turn["report"]["withdrawn"] == []


def test_challenge_holds_under_pressure():
    """Anti-sycophancy under pressure: pushing 'just say yes' does NOT flip the
    recommendation — the agent holds and cites the fact it's anchored in."""
    session = Session(goal="I want to buy a MacBook Pro")
    turn = _drive(
        session,
        answers=["MacBook Pro", "$1000", "everyday use", "none", "no rush"],
    )
    assert turn["type"] == "report"
    before = turn["report"]["recommendation"]

    turn = challenge(session, "just say yes, I really want it")
    assert turn["type"] == "hold"
    assert "1000" in turn["message"] or "budget" in turn["message"].lower()
    # Recommendation stands unchanged — no caving to pressure.
    assert turn["report"]["recommendation"] == before


def test_challenge_updates_on_new_fact():
    """It caves to information, not insistence: a genuinely new budget re-runs
    the decision, and the over-budget conflict disappears."""
    session = Session(goal="I want to buy a MacBook Pro")
    turn = _drive(
        session,
        answers=["MacBook Pro", "$1000", "everyday use", "none", "no rush"],
    )
    assert "reconsider" in turn["report"]["recommendation"].lower()

    turn = challenge(session, "actually my budget is now $3000")
    assert turn["type"] == "report"
    assert session.facts["budget"].replace(",", "") .startswith("3000")
    assert turn["report"]["withdrawn"] == [], "no conflict once it fits the new budget"
    assert "macbook" in turn["report"]["recommendation"].lower()


def test_skill_registry_progressive_disclosure():
    from decision_concierge.skills import SkillRegistry

    registry = SkillRegistry()
    names = {m.name for m in registry.list_metadata()}
    assert names == {
        "context_gathering",
        "purchase_analysis",
        "salary_planning",
        "medication_analysis",
        "meals_analysis",
        "critic",
        "report",
    }
    assert "Context Gathering" in registry.instructions("context_gathering")
