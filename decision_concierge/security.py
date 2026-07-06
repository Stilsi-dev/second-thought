"""Day 4 concepts, scaled down: least-privilege tool access, human-in-the-loop
gate for sensitive domains, and an append-only audit log with basic redaction."""

import json
import time
from pathlib import Path

from .config import SENSITIVE_DOMAINS

AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "audit_log.jsonl"

REDACT_KEYS = {
    "income", "monthly_income", "salary", "expenses",  # financial PII
    "current_meds", "allergies", "new_item",           # health PII (medication)
    "goal", "restrictions",                            # health PII (meals: diet goal, allergies)
}


def is_sensitive(domain: str | None) -> bool:
    return domain in SENSITIVE_DOMAINS


def redact(facts: dict) -> dict:
    """Never write raw financial figures to the audit trail — log shape, not values."""
    return {k: ("<redacted>" if k in REDACT_KEYS else v) for k, v in facts.items()}


def audit(event: str, session_domain: str | None, facts: dict | None = None):
    entry = {
        "ts": time.time(),
        "event": event,
        "domain": session_domain,
        "facts": redact(facts or {}),
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
