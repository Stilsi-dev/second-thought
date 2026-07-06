"""ADK entrypoint package. `adk web` / `adk run` scan sibling folders for a
package that exposes `root_agent`; importing `agent` here surfaces it."""

from . import agent  # noqa: F401
