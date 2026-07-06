"""Streamlit UI for Second Thought.

Deliberately thin: it only renders session state and forwards user input to
the orchestrator. The agent trace panel is the A2UI-style separation in
practice — the orchestrator returns structured data, this file decides how to
draw it.
"""

import streamlit as st

from decision_concierge.config import MOCK_MODE
from decision_concierge.memory import Session
from decision_concierge.orchestrator import advance, challenge
from decision_concierge.security import is_sensitive

st.set_page_config(page_title="Second Thought", page_icon="🧭")

st.title("🧭 Second Thought")
st.caption(
    "A decision concierge that thinks twice. Most AI agents rush to agree — this "
    "one interviews you first, then argues with its own recommendation before "
    "giving it to you."
)

if MOCK_MODE:
    st.warning(
        "No GEMINI_API_KEY set — running in mock mode. The full agent loop "
        "still runs; question phrasing and recommendations are templated "
        "instead of model-generated. Add a key to .env for the full demo."
    )


def privacy_panel():
    """Surfaces the safe-and-secure story the Concierge track asks for — the
    protections are enforced in code (see SECURITY.md); this makes them visible."""
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

if "session" not in st.session_state:
    st.session_state.session = None
    st.session_state.turn = None

if st.session_state.session is None:
    privacy_panel()
    goal = st.text_input(
        "What decision are you trying to make? (for yourself or someone you care for)",
        placeholder="e.g. I'm thinking about buying a MacBook Air M4",
    )
    if st.button("Start", type="primary") and goal.strip():
        st.session_state.session = Session(goal=goal.strip())
        st.session_state.turn = advance(st.session_state.session)
        st.rerun()
    st.stop()

session = st.session_state.session
turn = st.session_state.turn

with st.sidebar:
    st.subheader("Agent trace")
    for step in session.trace:
        st.write(f"- {step}")
    if session.domain:
        st.metric("Domain", session.domain)
        st.progress(session.confidence, text=f"Context confidence: {session.confidence:.0%}")
    if st.button("Restart (erases your answers)"):
        st.session_state.session = None
        st.session_state.turn = None
        st.rerun()
    privacy_panel()

if turn["type"] == "question":
    # Consent notice the first time a sensitive domain starts collecting data.
    if is_sensitive(session.domain):
        st.info(
            "🔒 This is a sensitive topic. Your answers stay in this session on "
            "your machine, are redacted from any log, and nothing is finalized "
            "without your confirmation."
        )
    st.write(f"**{turn['question']}**")
    reply = st.text_input("Your answer", key=f"reply_{len(session.trace)}")
    if st.button("Submit") and reply.strip():
        st.session_state.turn = advance(session, user_reply=reply.strip())
        st.rerun()

elif turn["type"] == "confirm":
    st.info(
        "This decision involves sensitive financial data. Review the draft "
        "below and confirm before Second Thought finalizes the report."
    )
    st.json(turn["draft"])
    if turn["critique"].get("issues"):
        st.warning("Critic flagged: " + "; ".join(turn["critique"]["issues"]))
    if st.button("Confirm and finalize", type="primary"):
        session.confirmed = True
        st.session_state.turn = advance(session)
        st.rerun()

def render_report(report):
    # The hero visual: when the agent caught and corrected its own advice, show
    # the contrast. This is the anti-sycophancy pitch made concrete — the "before"
    # is what a sycophantic assistant would have handed you.
    for w in report["withdrawn"]:
        st.error(f"❌ First take (withdrawn): {w['recommendation']}")
        for issue in w["caught_by"]:
            st.write(f"   ⚠️ Caught by your own facts: {issue}")
    if report["withdrawn"]:
        st.caption("↑ A sycophantic assistant would have stopped here. This one didn't.")

    st.success(f"✅ Recommendation: {report['recommendation']}")
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
    st.json(report["facts"])

    st.caption(
        f"Confidence: {report['confidence']} · Critic approved: {report['critic_approved']} "
        f"· Human confirmed: {report['human_confirmed']}"
    )

    # Challenge-back: let the user push. The agent holds its ground under mere
    # pressure and only re-evaluates if a genuinely new fact is supplied.
    st.divider()
    st.markdown("**Not convinced? Push back — or tell me what changed:**")
    push = st.text_input(
        "e.g. 'just say yes' — or 'actually my budget is now $2500'",
        key=f"push_{len(session.trace)}",
    )
    if st.button("Push back") and push.strip():
        st.session_state.turn = challenge(session, push.strip())
        st.rerun()


if turn["type"] == "report":
    render_report(turn["report"])

elif turn["type"] == "hold":
    st.warning(f"🛑 {turn['message']}")
    st.caption("It won't cave to pressure — only to new information.")
    render_report(turn["report"])
