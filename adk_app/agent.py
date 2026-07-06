"""Second Thought — Google ADK edition (course concept: Agent / Multi-agent + MCP).

This is a *second, framework-native* entrypoint that sits BESIDE the hand-written
pipeline in `decision_concierge/orchestrator.py` — it does not replace it. Same
domain logic, same MCP tools, but expressed in Google's Agent Development Kit so
the multi-agent structure is explicit:

    root coordinator (LlmAgent)
      ├── purchase specialist   ┐
      ├── salary specialist     │  each a sub-agent the root delegates to,
      ├── medication specialist │  all sharing the SAME real MCP tool server
      └── meals specialist      ┘

The tools are not reimplemented here. Every sub-agent talks to the exact MCP
stdio server in `decision_concierge/mcp_server/server.py` via ADK's `McpToolset`,
so ADK auto-discovers all five tools (affordability_calculator, budget_allocator,
product_price_lookup, drug_interaction_lookup, nutrition_lookup). One MCP server,
two clients: the custom `mcp_client.py` and now ADK.

Run it:
    adk web            # pick "adk_app" in the browser UI
    adk run adk_app    # terminal
    python -m adk_app.agent "should I buy a $1200 laptop on a $3000/mo income?"

Needs GOOGLE_API_KEY (or GEMINI_API_KEY) set — ADK drives a live Gemini model, so
unlike the mock-mode Streamlit app this path requires a key to actually reason.
The wiring/structure below is what demonstrates the ADK + MCP concepts in code.
"""

import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StdioConnectionParams,
)
from mcp import StdioServerParameters

from decision_concierge import config

# The model string is reused from the existing config so the ADK path and the
# Streamlit path stay on the same Gemini model (single knob, no drift).
_MODEL = config.GEMINI_MODEL


def _mcp_tools() -> McpToolset:
    """Launch the project's real MCP server over stdio and expose its five tools
    to ADK. Identical server binary the custom `mcp_client.call_tool` spawns —
    `python -m decision_concierge.mcp_server.server` — so there is one source of
    truth for tool behavior regardless of which client calls it."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,  # same interpreter -> same venv/deps
                args=["-m", "decision_concierge.mcp_server.server"],
            ),
            timeout=30,
        )
    )


# Each domain sub-agent is a specialist: same instinct as the corresponding
# skill folder under decision_concierge/skills/, but here it is an ADK agent the
# coordinator can transfer control to. They share one McpToolset instance so the
# whole app talks to a single MCP server subprocess.
_shared_tools = _mcp_tools()

purchase_agent = LlmAgent(
    name="purchase_specialist",
    model=_MODEL,
    description="Decides whether a discretionary purchase is affordable and wise.",
    instruction=(
        "You advise on a single purchase decision. Gather the item, its price, "
        "and the user's monthly income before judging. Use affordability_calculator "
        "and product_price_lookup. Argue with your own first instinct: state the "
        "recommendation, then the strongest risk against it. Never invent a price — "
        "if product_price_lookup returns no match, say the estimate is unverified."
    ),
    tools=[_shared_tools],
)

salary_agent = LlmAgent(
    name="salary_specialist",
    model=_MODEL,
    description="Plans an income allocation (savings/discretionary/buffer).",
    instruction=(
        "You plan how to allocate monthly income. Collect monthly income and fixed "
        "expenses, then call budget_allocator. This is sensitive financial data: "
        "present the plan as a suggestion, surface the trade-off you are least sure "
        "about, and never state figures the tool did not return."
    ),
    tools=[_shared_tools],
)

medication_agent = LlmAgent(
    name="medication_specialist",
    model=_MODEL,
    description="Flags interactions/allergies for an OTC medication or supplement.",
    instruction=(
        "You are an organizer aid, NOT a medical advisor. Collect the candidate "
        "item, current meds, and allergies, then call drug_interaction_lookup. "
        "Report any allergy hit or interaction plainly and tell the user to verify "
        "with a pharmacist. Never diagnose, prescribe, or call anything safe."
    ),
    tools=[_shared_tools],
)

meals_agent = LlmAgent(
    name="meals_specialist",
    model=_MODEL,
    description="Compares a food choice against the user's own stated goal.",
    instruction=(
        "You help compare a meal against the user's OWN stated goal (e.g. lower "
        "sugar, lower sodium). Collect the dish and the goal, call nutrition_lookup, "
        "and report the numbers against that goal. Never call a food 'healthy' or "
        "'unhealthy' as fact — report figures and let the goal decide."
    ),
    tools=[_shared_tools],
)

# The coordinator is the single front door (course concept: multi-agent system).
# It does no analysis itself — it classifies the request and transfers to the
# matching specialist, mirroring orchestrator.classify_domain() but delegating
# via ADK sub-agents instead of a hand-written skill-name branch.
root_agent = LlmAgent(
    name="second_thought_coordinator",
    model=_MODEL,
    description="Routes a personal decision to the right specialist and gives a second opinion.",
    instruction=(
        "You are Second Thought, a decision concierge. Read the user's goal and "
        "transfer to exactly one specialist: purchase_specialist for buying/"
        "affordability, salary_specialist for income/budget planning, "
        "medication_specialist for meds/supplements/interactions, meals_specialist "
        "for food/diet choices. Do not analyze yourself — delegate. If the request "
        "is ambiguous, ask one clarifying question first."
    ),
    sub_agents=[purchase_agent, salary_agent, medication_agent, meals_agent],
)


def _demo(goal: str) -> None:
    """Minimal terminal driver so the ADK agent is runnable without the `adk`
    CLI: `python -m adk_app.agent "<goal>"`. Uses ADK's Runner + in-memory
    session, the framework equivalents of orchestrator.advance() + memory.Session."""
    import asyncio

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    async def _run() -> None:
        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name="second_thought", user_id="demo", session_id="s1"
        )
        runner = Runner(
            agent=root_agent,
            app_name="second_thought",
            session_service=session_service,
        )
        message = types.Content(role="user", parts=[types.Part(text=goal)])
        async for event in runner.run_async(
            user_id="demo", session_id="s1", new_message=message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"[{event.author}] {part.text}")

    asyncio.run(_run())


if __name__ == "__main__":
    if config.MOCK_MODE:
        print(
            "No GEMINI_API_KEY/GOOGLE_API_KEY set. The ADK path needs a key to "
            "drive Gemini. The mock-mode demo is the Streamlit app: "
            "`streamlit run app.py`."
        )
        sys.exit(1)
    goal = " ".join(sys.argv[1:]) or "Should I buy a $1200 laptop on a $3000/mo income?"
    _demo(goal)
