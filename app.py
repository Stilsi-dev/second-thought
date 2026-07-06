"""Streamlit UI for Second Thought.

Deliberately thin: it only renders session state and forwards user input to the
orchestrator (no business logic lives here — that's in the skills). What it does
own is presentation, and the presentation is the pitch: PRODUCT.md asks the UI to
*show the second thought* and stay "staged, not chatty." So the interview reads
as a conversation, but it's wrapped in an explicit phase stepper and a toggleable
"agent thinking" trace — legible staged progress, never a bare chatbot stream.
"""

import html

import streamlit as st

from decision_concierge.config import MOCK_MODE
from decision_concierge.memory import Session
from decision_concierge.orchestrator import advance, challenge
from decision_concierge.security import is_sensitive

st.set_page_config(page_title="Second Thought", page_icon="🧭", layout="centered")


# ── Styling ────────────────────────────────────────────────────────────────
# One injected stylesheet. Custom classes (stepper, thinking, facts, verdicts)
# get bespoke markup so the CSS is stable rather than riding Streamlit internals.
st.markdown(
    """
    <style>
      :root {
        --ink: #1b2230; --muted: #56607a; --line: #dfe3eb;
        --accent: #4457b3; --accent-soft: #eef1fb;
        --withdrawn: #b23b2e; --approved: #1f7a4d;
        --panel: #ffffff; --panel-2: #f2f4f8;
      }
      .block-container { max-width: 720px; padding-top: 2.2rem; }
      h1 { letter-spacing: -0.02em; font-weight: 700; }

      /* Phase stepper — makes the pipeline legible (staged, not chatty) */
      .st-stepper { display: flex; gap: .35rem; margin: .25rem 0 1.4rem;
        flex-wrap: wrap; align-items: center; }
      .st-step { display: flex; align-items: center; gap: .45rem;
        font-size: .8rem; color: var(--muted); }
      .st-step .dot { width: 1.35rem; height: 1.35rem; border-radius: 50%;
        display: grid; place-items: center; font-size: .72rem; font-weight: 600;
        border: 1.5px solid var(--line); background: var(--panel); color: var(--muted);
        transition: all .18s ease-out; }
      .st-step.done .dot { background: var(--approved); border-color: var(--approved); color:#fff; }
      .st-step.active .dot { background: var(--accent); border-color: var(--accent); color:#fff; }
      .st-step.active { color: var(--ink); font-weight: 600; }
      .st-sep { flex: 1 1 12px; height: 1.5px; background: var(--line); min-width: 12px; }

      /* Agent thinking trace */
      .thinking { background: var(--panel-2); border: 1px solid var(--line);
        border-radius: 12px; padding: .85rem 1rem; margin: .3rem 0 1rem; }
      .thinking h4 { margin: 0 0 .55rem; font-size: .78rem; letter-spacing: .02em;
        text-transform: uppercase; color: var(--muted); font-weight: 600; }
      .thinking ol { margin: 0; padding-left: 1.1rem; }
      .thinking li { font-size: .86rem; color: var(--ink); margin: .2rem 0;
        line-height: 1.45; font-variant-numeric: tabular-nums; }
      .thinking li::marker { color: var(--accent); font-weight: 600; }
      .phase { margin: .1rem 0 .7rem; }
      .phase:last-child { margin-bottom: 0; }
      .phase .p-head { font-size: .74rem; font-weight: 700; letter-spacing: .04em;
        text-transform: uppercase; color: var(--accent); margin-bottom: .25rem;
        display: flex; align-items: center; gap: .4rem; }
      .phase .p-head::before { content: ""; width: .5rem; height: .5rem;
        border-radius: 50%; background: var(--accent); }

      /* MCP tool receipts — the invisible tool I/O, made visible */
      .tool-card { background: var(--panel); border: 1px solid var(--line);
        border-radius: 9px; padding: .45rem .65rem; margin: .3rem 0 .3rem 1.1rem;
        display: flex; flex-direction: column; gap: .1rem; }
      .tool-card .tname { font-size: .74rem; color: var(--accent);
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; }
      .tool-card .thead { font-size: .86rem; color: var(--ink);
        font-variant-numeric: tabular-nums; }

      /* Before/after self-correction diff */
      .diff { display: grid; grid-template-columns: 1fr auto 1fr; gap: .7rem;
        align-items: stretch; margin: .5rem 0; }
      .diff .side { border-radius: 12px; padding: .8rem .9rem; border: 1px solid var(--line); }
      .diff .before { background: #fbf1ef; border-color: #ecccc6; }
      .diff .after  { background: #eef7f1; border-color: #cfe6d8; }
      .diff .side .tag { font-weight: 700; font-size: .82rem; margin-bottom: .3rem; }
      .diff .before .tag { color: var(--withdrawn); }
      .diff .after  .tag { color: var(--approved); }
      .diff .arrow { display: grid; place-items: center; color: var(--muted); font-size: 1.1rem; }
      .diff .caught { color: var(--withdrawn); font-size: .8rem; margin-top: .4rem; }
      @media (max-width: 560px) {
        .diff { grid-template-columns: 1fr; }
        .diff .arrow { transform: rotate(90deg); }
      }

      /* Honest reveal: stagger the already-computed trace as it paints in */
      .thinking li, .tool-card { animation: tk-in .32s ease-out backwards; }
      .thinking li:nth-child(2){animation-delay:.04s} .thinking li:nth-child(3){animation-delay:.08s}
      .thinking li:nth-child(4){animation-delay:.12s} .thinking li:nth-child(5){animation-delay:.16s}
      .tool-card:nth-child(2){animation-delay:.1s} .tool-card:nth-child(3){animation-delay:.2s}
      @keyframes tk-in { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }

      /* Verdict blocks (color + icon + text — never color alone) */
      .verdict { border-radius: 12px; padding: .9rem 1.05rem; margin: .5rem 0;
        border: 1px solid var(--line); }
      .verdict.withdrawn { background: #fbf1ef; border-color: #ecccc6; }
      .verdict.approved  { background: #eef7f1; border-color: #cfe6d8; }
      .verdict .label { font-weight: 700; font-size: .95rem; }
      .verdict.withdrawn .label { color: var(--withdrawn); }
      .verdict.approved  .label { color: var(--approved); }
      .verdict .sub { color: var(--muted); font-size: .82rem; margin-top: .3rem; }

      /* Facts — a clean definition list, not a raw JSON dump */
      .facts { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
      .fact-row { display: flex; justify-content: space-between; gap: 1rem;
        padding: .5rem .85rem; font-size: .87rem; }
      .fact-row:nth-child(odd) { background: var(--panel-2); }
      .fact-row .k { color: var(--muted); }
      .fact-row .v { color: var(--ink); font-weight: 600; text-align: right;
        font-variant-numeric: tabular-nums; }

      .receipts { color: var(--muted); font-size: .78rem; margin-top: .6rem;
        font-variant-numeric: tabular-nums; }

      /* Chat bubbles — user right, AI left */
      .chat { display: flex; flex-direction: column; gap: .5rem; margin: .2rem 0 1rem; }
      .msg { display: flex; gap: .5rem; max-width: 85%; align-items: flex-end; }
      .msg.ai { align-self: flex-start; }
      .msg.user { align-self: flex-end; flex-direction: row-reverse; }
      .msg .avatar { font-size: 1.05rem; line-height: 1.9; flex: 0 0 auto; }
      .msg .bubble { padding: .55rem .8rem; border-radius: 15px; font-size: .92rem;
        line-height: 1.45; word-break: break-word; }
      .msg.ai .bubble { background: var(--panel-2); border: 1px solid var(--line);
        color: var(--ink); border-bottom-left-radius: 5px; }
      .msg.user .bubble { background: var(--accent); color: #fff;
        border-bottom-right-radius: 5px; }

      /* Landing "how it works" strip — teaches the staged loop, calm not salesy.
         Reuses the numbered-dot language of the in-flow pipeline for recognition. */
      .howto { margin: .2rem 0 1.5rem; }
      .howto .h-title { font-size: .74rem; text-transform: uppercase;
        letter-spacing: .05em; color: var(--muted); font-weight: 700; margin-bottom: .7rem; }
      .howto .steps { display: flex; gap: .5rem; align-items: stretch; }
      .howto .step { flex: 1 1 0; display: flex; flex-direction: column; gap: .3rem; }
      .howto .step .n { width: 1.5rem; height: 1.5rem; border-radius: 50%;
        background: var(--accent-soft); color: var(--accent); display: grid;
        place-items: center; font-weight: 700; font-size: .8rem;
        border: 1.5px solid var(--accent); }
      .howto .step .lbl { font-weight: 600; font-size: .87rem; color: var(--ink); }
      .howto .step .desc { font-size: .78rem; color: var(--muted); line-height: 1.35; }
      .howto .arrow { color: var(--line); align-self: center; font-size: 1.1rem;
        padding-bottom: 1.1rem; }
      @media (max-width: 560px) {
        .howto .steps { flex-direction: column; }
        .howto .arrow { transform: rotate(90deg); padding: 0; align-self: flex-start;
          margin-left: .5rem; }
      }

      /* Contained entry box header — focused, composed (NOT a gradient chatbot hero) */
      .entry-head { text-align: center; margin: .1rem 0 1.2rem; }
      .entry-head .eh-title { font-size: 1.18rem; font-weight: 700; color: var(--ink);
        letter-spacing: -.01em; }
      .entry-head .eh-sub { font-size: .88rem; color: var(--muted); margin: .35rem auto 0;
        line-height: 1.45; max-width: 48ch; }
      /* Give the bordered entry container a touch more presence */
      [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }

      @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def esc(x) -> str:
    return html.escape(str(x))


# ── Header ─────────────────────────────────────────────────────────────────
st.title("🧭 Second Thought")
st.caption(
    "A decision concierge that thinks twice. Most AI agents rush to agree — this "
    "one interviews you first, then argues with its own recommendation before "
    "giving it to you."
)

if MOCK_MODE:
    st.info(
        "Running in **mock mode** (no API key). The full agent loop still runs — "
        "interview, MCP tool calls, self-critique, gating — only the wording is "
        "templated instead of model-generated.",
        icon="🧪",
    )


# ── State ──────────────────────────────────────────────────────────────────
if "session" not in st.session_state:
    st.session_state.session = None
    st.session_state.turn = None
    st.session_state.messages = []       # UI-only interview transcript
    st.session_state.show_thinking = True


def phase_of(turn) -> str:
    return {"question": "Interview", "confirm": "Confirm",
            "report": "Report", "hold": "Report"}.get(turn["type"], "Interview")


def stepper(current: str, sensitive: bool):
    steps = ["Interview", "Analysis", "Critique"]
    if sensitive:
        steps.append("Confirm")
    steps.append("Report")
    idx = steps.index(current) if current in steps else 0
    html_parts = ['<div class="st-stepper">']
    for i, s in enumerate(steps):
        cls = "done" if i < idx else ("active" if i == idx else "")
        mark = "✓" if i < idx else str(i + 1)
        html_parts.append(
            f'<span class="st-step {cls}"><span class="dot">{mark}</span>{s}</span>'
        )
        if i < len(steps) - 1:
            html_parts.append('<span class="st-sep"></span>')
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "—"


def tool_receipts(tool_data: dict) -> str:
    """Turn the raw MCP tool output riding on the draft into readable receipt
    cards — the actual tool I/O the pipeline ran, which was otherwise invisible."""
    cards = []
    if "catalog" in tool_data:
        c = tool_data.get("catalog") or {}
        head = (f'{esc(c.get("match", "item"))} · {_money(c.get("price"))} · '
                f'{esc(c.get("rating", "?"))}★') if c.get("price") is not None \
            else esc(c.get("note", "no catalog match — unverified estimate"))
        cards.append(("product_price_lookup", head))
    if "budget_fit" in tool_data:
        b = tool_data.get("budget_fit") or {}
        pct = b.get("pct_of_income")
        head = f'{pct}% of income · {esc(b.get("verdict", "?"))}' if pct is not None \
            else "income unknown"
        cards.append(("affordability_calculator", head))
    if "allocation" in tool_data:
        a = tool_data.get("allocation") or {}
        head = (f'save {_money(a.get("savings_target"))} · '
                f'spend {_money(a.get("discretionary"))} · '
                f'buffer {_money(a.get("buffer"))}')
        cards.append(("budget_allocator", head))
    if "interaction" in tool_data:
        i = tool_data.get("interaction") or {}
        hits = []
        if i.get("allergy_hit"):
            hits.append(f'⚠ allergy: {esc(i["allergy_hit"])}')
        if i.get("interactions"):
            hits.append("⚠ interacts with " + esc(", ".join(i["interactions"])))
        cards.append(("drug_interaction_lookup", " · ".join(hits) if hits else "no conflicts found"))
    if "nutrition" in tool_data:
        n = tool_data.get("nutrition") or {}
        if n.get("calories") is not None:
            head = f'{n.get("calories")} cal · {n.get("sugar_g")}g sugar · {n.get("sodium_mg")}mg sodium'
            if n.get("allergens"):
                head += f' · allergens: {esc(", ".join(n["allergens"]))}'
        else:
            head = esc(n.get("note", "no match — unverified"))
        cards.append(("nutrition_lookup", head))
    return "".join(
        f'<div class="tool-card"><span class="tname">🔧 {esc(name)}</span>'
        f'<span class="thead">{head}</span></div>'
        for name, head in cards
    )


_PHASES = ["Classify", "Interview", "Analyze", "Critique", "Confirm", "Report", "Challenge"]


def _phase_of_step(s: str) -> str:
    if s.startswith("Coordinator"):
        return "Classify"
    if s.startswith("Context Gathering"):
        return "Interview"
    if s.startswith("Critic"):
        return "Critique"
    if s.startswith("Security gate"):
        return "Confirm"
    if s.startswith("Report skill"):
        return "Report"
    if s.startswith("Challenge"):
        return "Challenge"
    return "Analyze"  # "<domain>_analysis skill: analyzing", re-analyze, etc.


def thinking_panel(session):
    """The hero: the real agent-loop trace, grouped by phase, with the MCP tool
    receipts surfaced under Analyze. Shown when the toggle is on."""
    if not st.session_state.show_thinking or not session.trace:
        return
    buckets: dict[str, list[str]] = {}
    for step in session.trace:
        buckets.setdefault(_phase_of_step(step), []).append(step)
    tool_html = tool_receipts(session.draft.get("_tool_data", {})) if session.draft else ""

    blocks = []
    for phase in _PHASES:
        steps = buckets.get(phase)
        if not steps and not (phase == "Analyze" and tool_html):
            continue
        items = "".join(f"<li>{esc(s)}</li>" for s in (steps or []))
        extra = tool_html if phase == "Analyze" else ""
        blocks.append(
            f'<div class="phase"><div class="p-head">{phase}</div>'
            f'<ol>{items}</ol>{extra}</div>'
        )
    # Collapsible in place — click the header to fold the trace away.
    with st.expander("🧠 Agent thinking", expanded=True):
        st.markdown(
            f'<div class="thinking">{"".join(blocks)}</div>',
            unsafe_allow_html=True,
        )


def privacy_panel():
    with st.expander("🔒 Your privacy — what happens to your data"):
        st.markdown(
            "- **Nothing leaves your machine in mock mode** (no API key = no network calls).\n"
            "- **Nothing sensitive is stored.** Your answers live only in this session; "
            "*Restart* erases them.\n"
            "- **The audit log is redacted** — income, expenses, medications, and "
            "allergies are never written to disk in the clear.\n"
            "- **Sensitive decisions need your confirmation** before anything is finalized.\n\n"
            "Details: see `SECURITY.md`."
        )


# ── Landing (no session yet) ───────────────────────────────────────────────
if st.session_state.session is None:
    # The entry point lives in its own contained box — focused, on-brand. NOT a
    # gradient/sparkle chatbot hero (PRODUCT.md bans generic chatbot UI); the
    # how-it-works strip inside is what marks it a staged decision tool.
    with st.container(border=True):
        st.markdown(
            '<div class="entry-head">'
            '<div class="eh-title">🧭 Start a decision</div>'
            '<div class="eh-sub">Tell me what you\'re weighing. I\'ll interview you, '
            'check the facts with real tools, and argue with my own answer before I '
            'hand it over.</div></div>',
            unsafe_allow_html=True,
        )

        # "How it works" — teach the staged loop up front so a first-time viewer
        # recognizes the machinery when it runs. Same numbered-dot language as the
        # in-flow pipeline. Steps use CONTEXT.md's canonical behavior, plainly said.
        howto_steps = [
            ("1", "Interview", "Asks before it answers."),
            ("2", "Investigate", "Looks up real numbers with tools."),
            ("3", "Second thought", "Argues with its own draft, corrects itself."),
            ("4", "Report", "A recommendation you can trace."),
        ]
        cells = []
        for i, (n, lbl, desc) in enumerate(howto_steps):
            cells.append(
                f'<div class="step"><div class="n">{n}</div>'
                f'<div class="lbl">{esc(lbl)}</div><div class="desc">{esc(desc)}</div></div>'
            )
            if i < len(howto_steps) - 1:
                cells.append('<div class="arrow">→</div>')
        st.markdown(
            f'<div class="howto"><div class="h-title">How it works</div>'
            f'<div class="steps">{"".join(cells)}</div></div>',
            unsafe_allow_html=True,
        )

        goal = st.text_input(
            "What decision are you trying to make? (for yourself or someone you care for)",
            placeholder="e.g. I'm thinking about buying a MacBook Air M4",
        )
        # Examples span all four Domains. Each goal is phrased in a real user's
        # first-person voice AND contains a keyword the mock-mode classifier routes
        # on (see orchestrator.classify_domain) — so they route correctly even on
        # the keyless deployed demo.
        st.caption("Or start from an example:")
        examples = {
            "A purchase": "I'm thinking about buying a MacBook Air M4",
            "A paycheck": "I just got paid — help me split my paycheck",
            "A medication": "Can I take ibuprofen with my prescription meds?",
            "A meal": "Is instant ramen a smart meal if I'm watching sodium?",
        }
        picked = None
        for col, (lbl, ex) in zip(st.columns(4), examples.items()):
            if col.button(lbl, use_container_width=True):
                picked = ex
        goal = picked or goal
        start = st.button("Start", type="primary", use_container_width=True)

    if (start or picked) and goal and goal.strip():
        st.session_state.session = Session(goal=goal.strip())
        st.session_state.messages = [("user", goal.strip())]
        st.session_state.turn = advance(st.session_state.session)
        st.rerun()
    privacy_panel()
    st.stop()


session = st.session_state.session
turn = st.session_state.turn
sensitive = is_sensitive(session.domain)


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Second Thought")
    st.session_state.show_thinking = st.toggle(
        "Show agent thinking", value=st.session_state.show_thinking,
        help="Stream the agent's reasoning trace as it works.",
    )
    if session.domain:
        st.metric("Domain", session.domain.title())
        st.progress(
            min(session.confidence, 1.0),
            text=f"Context confidence · {session.confidence:.0%}",
        )
    st.divider()
    if st.button("↺ Restart (erases your answers)", use_container_width=True):
        for k in ("session", "turn", "messages"):
            st.session_state[k] = None if k != "messages" else []
        st.rerun()
    privacy_panel()


# ── Phase stepper + thinking ───────────────────────────────────────────────
stepper(phase_of(turn), sensitive)
if sensitive and turn["type"] == "question":
    st.caption("🔒 Sensitive topic — answers stay in this session, redacted from logs, "
               "and nothing is finalized without your confirmation.")

# Conversation transcript (the answered interview so far) — user right, AI left.
def _bubble(role: str, content: str) -> str:
    cls, av = ("user", "🧑") if role == "user" else ("ai", "🧭")
    return (f'<div class="msg {cls}"><span class="avatar">{av}</span>'
            f'<div class="bubble">{esc(content)}</div></div>')


def render_chat(pending_ai: str | None = None):
    rows = [_bubble(r, c) for r, c in st.session_state.messages]
    if pending_ai:
        rows.append(_bubble("assistant", pending_ai))
    if rows:
        st.markdown(f'<div class="chat">{"".join(rows)}</div>', unsafe_allow_html=True)


if turn["type"] != "question":
    render_chat()  # history above the confirm/report panel


# ── Turn rendering ─────────────────────────────────────────────────────────
if turn["type"] == "question":
    render_chat(pending_ai=turn["question"])
    thinking_panel(session)
    reply = st.chat_input("Type your answer…")
    if reply and reply.strip():
        st.session_state.messages.append(("assistant", turn["question"]))
        st.session_state.messages.append(("user", reply.strip()))
        st.session_state.turn = advance(session, user_reply=reply.strip())
        st.rerun()

elif turn["type"] == "confirm":
    thinking_panel(session)
    st.warning(
        "This decision involves sensitive data. Review the draft below and confirm "
        "before Second Thought finalizes the report.",
        icon="🔒",
    )
    with st.expander("Draft under review", expanded=True):
        st.json(turn["draft"])
    if turn["critique"].get("issues"):
        st.warning("Critic flagged: " + "; ".join(turn["critique"]["issues"]))
    if st.button("Confirm and finalize", type="primary"):
        session.confirmed = True
        st.session_state.turn = advance(session)
        st.rerun()


def render_report(report):
    thinking_panel(session)

    # Hero: when the agent caught and corrected its own advice, show it as a true
    # before/after. This is the anti-sycophancy pitch made concrete.
    withdrawn = report["withdrawn"]
    if withdrawn:
        w = withdrawn[0]
        caught = "".join(f"<li>{esc(i)}</li>" for i in w["caught_by"])
        st.markdown(
            '<div class="diff">'
            '<div class="side before"><div class="tag">✕ First take, withdrawn</div>'
            f'<div>{esc(w["recommendation"])}</div>'
            f'<ul class="caught" style="margin:.35rem 0 0 .9rem">{caught}</ul></div>'
            '<div class="arrow">→</div>'
            '<div class="side after"><div class="tag">✓ Corrected recommendation</div>'
            f'<div>{esc(report["recommendation"])}</div></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.caption("↑ A sycophantic assistant would have handed you the first take. "
                   "This one caught it against your own facts, and corrected itself.")
    else:
        st.markdown(
            f'<div class="verdict approved"><span class="label">✓ Recommendation</span>'
            f'<div>{esc(report["recommendation"])}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(f"**What this saved you:** {report['value']}")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Reasoning**")
        for r in report["reasoning"]:
            st.write(f"- {r}")
    with col2:
        st.markdown("**Risks**")
        if report["risks"]:
            for r in report["risks"]:
                st.write(f"- {r}")
        else:
            st.write("None identified")

    if report["alternatives"]:
        st.markdown("**Alternatives**")
        for a in report["alternatives"]:
            st.write(f"- {a}")

    st.markdown("**Facts used**")
    rows = "".join(
        f'<div class="fact-row"><span class="k">{esc(k)}</span>'
        f'<span class="v">{esc(v)}</span></div>'
        for k, v in report["facts"].items()
    )
    st.markdown(f'<div class="facts">{rows}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="receipts">Confidence: {esc(report["confidence"])} · '
        f'Critic approved: {esc(report["critic_approved"])} · '
        f'Human confirmed: {esc(report["human_confirmed"])}</div>',
        unsafe_allow_html=True,
    )

    # Challenge-back: the agent holds its ground under pressure, re-evaluates on
    # new information only.
    st.divider()
    st.markdown("**Not convinced? Push back — or tell me what changed:**")
    push = st.chat_input("e.g. 'just say yes' — or 'actually my budget is now $2500'")
    if push and push.strip():
        st.session_state.turn = challenge(session, push.strip())
        st.rerun()


if turn["type"] == "report":
    render_report(turn["report"])

elif turn["type"] == "hold":
    st.warning(f"🛑 {turn['message']}")
    st.caption("It won't cave to pressure — only to new information.")
    render_report(turn["report"])
