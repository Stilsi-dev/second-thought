# Second Thought

*(Product name; the Python package remains `decision_concierge`.)*

A skill-based AI concierge that refuses to answer a decision until it has
gathered enough context, then investigates, self-checks, and returns a
structured recommendation. Ships four decision domains — buying something,
allocating a paycheck, starting a medication/supplement, and an everyday food
choice — spanning big occasional decisions and small daily ones, to show the
engine is one behavior fired in many places, not a bag of features.

## Language

**Second Thought**:
The whole system (product name) — one Coordinator agent plus a library of
Skills that together turn a vague goal into a Decision Report. The name refers
to its defining behavior: it gives an answer, then has a second thought and
corrects itself. The Python package is `decision_concierge`.
_Avoid_: assistant, chatbot, bot, Decision Concierge (old name).

**Domain**:
The kind of decision being made. Four exist today: **purchase**, **salary**,
**medication**, and **meals** (an everyday food choice). A Domain determines
which domain Skill and which required context fields apply. `salary`,
`medication`, and `meals` are Sensitive domains.
_Avoid_: category, module, track.

**Coordinator**:
The orchestrator that runs the agent loop — classifies the Domain, sequences
Skills, and enforces the loop guards. It holds no domain knowledge itself.
_Avoid_: router, controller, manager.

**Interview**:
The Context Gathering phase where the concierge asks the user for missing
context, one question at a time, before any recommendation is made.
_Avoid_: form, questionnaire, survey.

**Confidence floor**:
The guaranteed-complete baseline of context — every required field for the
Domain must be filled. The confidence bar measures progress against this
floor and reaches 100% when the floor is met. Drives MOCK_MODE and is a hard
minimum in every mode.
_Avoid_: threshold (the numeric cutoff is a separate config knob).

**Deepening probe**:
An optional extra follow-up question the LLM may ask *beyond* the floor to
sharpen understanding (capped at two). Shown in the trace as "deepening"; does
not count against the confidence bar.
_Avoid_: follow-up, extra question (use this canonical term).

**Draft**:
A domain Skill's proposed recommendation before the Critic has checked it and
before it becomes a Report.
_Avoid_: result, output, answer.

**Critic**:
The Skill that checks a Draft against the user's own stated facts for
contradictions. Runs a deterministic **Contradiction check** floor (always,
both modes) plus optional LLM nuance when a client exists. On rejection it
triggers exactly one Re-analyze.
_Avoid_: reviewer, validator, judge.

**Contradiction check**:
A domain-owned rule (`check(session, draft)` beside the domain Skill's `run`)
that deterministically catches a Draft that conflicts with a stated fact —
e.g. a recommended item priced over the stated budget, or a salary plan that
grows savings while ignoring stated debt. This is what makes "the agent argues
with its own recommendation" fire offline, not just with an API key.
_Avoid_: validation, guard, assertion.

**Re-analyze**:
The self-correction loop: a Critic rejection re-runs the domain Skill once
with the critique injected as extra context, producing a corrected Draft.
Capped at one pass; if the second Draft still fails, it ships flagged.
_Avoid_: retry, redo, loop.

**Challenge**:
A user pushing back on a finished Decision Report. The concierge distinguishes
**pressure** (insistence with no new fact → it Holds) from **new information**
(a changed fact → it re-evaluates honestly). It caves to information, never to
insistence. Handled by `orchestrator.challenge()`.
_Avoid_: complaint, objection, retry.

**Hold**:
The response to a Challenge that carries no new fact — the concierge keeps its
recommendation and cites the stated fact it's anchored in, rather than flipping
to please the user. The sharpest expression of the anti-sycophancy stance.
_Avoid_: refusal, rejection, denial.

**Decision Report**:
The final structured output — recommendation, reasoning, risks, alternatives,
confidence, the flags (critic-approved, human-confirmed), and any Withdrawn
drafts. Assembled deterministically; never model-written.
_Avoid_: summary, result, response.

**Withdrawn draft**:
A recommendation the concierge gave first and then retracted after its own
Contradiction check caught it. The Report surfaces these as a before/after
contrast — the "before" is what a sycophantic assistant would have handed you.
Present only when a Re-analyze actually happened; the contrast shows only when
earned.
_Avoid_: rejected, discarded, old draft.

**Sensitive domain**:
A Domain whose output is gated behind explicit human confirmation before the
Report is finalized. Currently `salary`, `medication`, and `meals` (the three
domains carrying financial or health stakes); `purchase` is the only
non-sensitive Domain.
_Avoid_: private, protected, secure.

## Example dialogue

> **Dev:** User says "help me with my paycheck." What happens first?
> **Concierge:** The Coordinator classifies the Domain as `salary`, then the
> Interview starts. It won't produce a Draft until the confidence floor is
> met — income, fixed expenses, savings, debt, goal all filled.
> **Dev:** What if the user volunteers something odd, like a big one-off bill?
> **Concierge:** With an API key, the LLM can fire a deepening probe (up to
> two) to pin that down. Without a key, it sticks to the floor questions.
> **Dev:** Then it just answers?
> **Concierge:** It produces a Draft, the Critic checks it against the stated
> facts. If the Draft ignores the debt the user mentioned, the Critic rejects
> it and one Re-analyze runs with that critique. Because `salary` is a
> sensitive domain, the corrected Draft still waits on human confirmation
> before becoming the Decision Report.
