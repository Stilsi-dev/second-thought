"""Session-scoped memory (context engineering, Day 1). Nothing persisted to
disk except the audit log — sensitive financial data stays in-session only."""

from dataclasses import dataclass, field


@dataclass
class Session:
    goal: str = ""
    domain: str | None = None          # "purchase" | "salary"
    facts: dict = field(default_factory=dict)      # collected interview answers
    confidence: float = 0.0            # progress against the required-fields floor
    pending_field: str | None = None
    sufficient: bool = False           # LLM judged context deep enough (ceiling)
    probe_count: int = 0               # deepening probes asked beyond the floor (cap 2)
    trace: list[str] = field(default_factory=list)  # agent-loop step log for UI
    draft: dict | None = None          # domain skill output
    draft_attempts: int = 0            # domain-skill runs; Re-analyze capped at 1 retry
    withdrawn: list = field(default_factory=list)  # rejected drafts + what caught them
    critique: dict | None = None       # critic skill output
    confirmed: bool = False            # human-in-the-loop gate (Day 4)
    report: dict | None = None

    def log(self, step: str):
        self.trace.append(step)
