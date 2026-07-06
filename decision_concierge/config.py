"""Env/config + Gemini client factory. Mock mode kicks in with no API key so the
whole agent loop still runs (and is demoable) without credentials."""

import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MOCK_MODE = GEMINI_API_KEY == ""

CONFIDENCE_THRESHOLD = 0.8
# Domains gated behind human confirmation before finalizing (health + financial PII).
SENSITIVE_DOMAINS = {"salary", "medication", "meals"}
MAX_DEEPENING_PROBES = 2  # LLM follow-ups allowed beyond the required-fields floor
MAX_REANALYZE = 1  # critic-rejection re-runs of a domain skill before shipping flagged

# Domain -> the skill that analyzes it. Shared by the orchestrator (to run it)
# and the critic (to call its deterministic check()). Add a domain here once.
DOMAIN_SKILL = {
    "purchase": "purchase_analysis",
    "salary": "salary_planning",
    "medication": "medication_analysis",
    "meals": "meals_analysis",
}


def get_client():
    """Returns a genai.Client, or None if running in mock mode."""
    if MOCK_MODE:
        return None
    from google import genai

    return genai.Client(api_key=GEMINI_API_KEY)
