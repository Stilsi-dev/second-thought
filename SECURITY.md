# Security & Privacy

Second Thought is a **Concierge Agents** submission, and that track's
defining requirement is keeping personal information *safe and secure*. This
project handles sensitive personal data — income, debt, medications, allergies,
and dietary/health goals — so privacy is a first-class design constraint, not an
afterthought. This document maps each protection to the code that enforces it.
Sensitive domains today: `salary`, `medication`, `meals`.

## Principles

1. **Sensitive data never leaves your machine.** With no API key the entire
   agent loop runs locally in `MOCK_MODE` — no network calls at all. With a key,
   only the minimum context needed for a single reasoning step is sent to Gemini.
2. **Nothing sensitive is persisted.** Collected facts live only in an in-memory
   `Session` for the duration of the conversation. Closing/restarting clears them.
3. **The audit trail is redacted.** The one thing written to disk (an operational
   audit log) has financial and health values stripped before writing.
4. **High-stakes decisions require a human.** Sensitive domains are gated behind
   explicit human confirmation before any recommendation is finalized.

## Protections, mapped to code

| Protection | Where | What it does |
|---|---|---|
| Local-only / no-network mode | [`config.py`](decision_concierge/config.py) `MOCK_MODE` | With no `GEMINI_API_KEY`, `get_client()` returns `None` and no data is ever sent off-device. |
| Secrets never in code | [`.env.example`](.env.example), [`.gitignore`](.gitignore) | The key is read from `.env` (gitignored); only a blank example is committed. |
| In-session-only memory | [`memory.py`](decision_concierge/memory.py) `Session` | Facts live in a dataclass held in Streamlit session state; never written to disk. |
| Human-in-the-loop gate | [`security.py`](decision_concierge/security.py) `SENSITIVE_DOMAINS`, [`orchestrator.py`](decision_concierge/orchestrator.py) | `salary`, `medication`, and `meals` block on explicit confirmation before finalizing. |
| Audit-log redaction | [`security.py`](decision_concierge/security.py) `REDACT_KEYS`, `redact()` | Income, expenses, current meds, allergies, and the candidate item are replaced with `<redacted>` before the audit line is written. |
| Least context to the model | domain skills + `_util.generate_json` | Prompts carry only the facts needed for the current step, not the whole session. |

## What is written to disk, exactly

Only `audit_log.jsonl` (gitignored), one JSON line per agent event, of the form:

```json
{"ts": 1751780000.0, "event": "draft_created", "domain": "medication",
 "facts": {"new_item": "<redacted>", "current_meds": "<redacted>",
           "allergies": "<redacted>", "reason": "pain"}}
```

Note the sensitive keys are `<redacted>`; only non-identifying context (like a
free-text reason) survives, and even that can be added to `REDACT_KEYS`.

## Deliberate tradeoff: no cross-session memory

A "true" concierge might remember you between visits. We deliberately **do not**
persist anything sensitive across sessions — for this track, provable privacy
beats convenience. Long-term memory, if ever added, would be opt-in and
encrypted at rest; today the safe default is to forget.

## Medication domain: not medical advice

The medication domain is a preparation/organizer aid. It only checks a candidate
against the user's *own stated* allergies and current medications, never
diagnoses or prescribes, and always defers the decision to a pharmacist or
physician. See [`skills/medication_analysis/SKILL.md`](decision_concierge/skills/medication_analysis/SKILL.md).
