"""
Browser backend registry.

Provides get_backend(name, agent) to instantiate the correct adapter.
New backends are added here with a simple import + dict entry.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent
    from python.helpers.browser_backend import BrowserBackend


def get_backend(name: str, agent: "Agent") -> "BrowserBackend":
    """Instantiate and return the requested browser backend adapter."""

    if name == "playwright":
        from python.helpers.backends.playwright_backend import PlaywrightBackend
        return PlaywrightBackend(agent)

    elif name == "openbrowser":
        from python.helpers.backends.openbrowser_backend import OpenBrowserBackend
        return OpenBrowserBackend(agent)

    elif name == "browser_use":
        # Return None sentinel — browser_agent.py uses its own State class
        # for browser_use to preserve full existing behavior
        return None  # type: ignore[return-value]

    else:
        raise ValueError(
            f"Unknown browser backend: '{name}'. "
            f"Available: browser_use, playwright, openbrowser"
        )
