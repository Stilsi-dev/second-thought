"""Small helpers shared by the domain/critic/report skills — parsing free-text
amounts and calling Gemini in JSON mode with a graceful mock fallback."""

import json
import re

from ..config import GEMINI_MODEL


def parse_amount(text: str) -> float:
    """'$1,200' / '50k' / '1200 pesos' -> 1200.0 (best-effort, defaults to 0)."""
    if not text:
        return 0.0
    text = text.lower().replace(",", "")
    match = re.search(r"[\d.]+", text)
    if not match:
        return 0.0
    value = float(match.group())
    if "k" in text:
        value *= 1000
    return value


def generate_json(client, instructions: str, prompt: str, mock: dict) -> dict:
    """Calls Gemini with response_mime_type=application/json; falls back to a
    deterministic mock payload if no client (no API key) or the call fails."""
    if client is None:
        return mock

    from google.genai import types

    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=instructions,
                response_mime_type="application/json",
            ),
        )
        return json.loads(resp.text)
    except Exception:
        return mock
