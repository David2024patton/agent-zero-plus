"""
Pluggable browser backend system for Agent Zero.

Provides a base class (BrowserBackend) and unified result type (BrowserResult)
that all browser automation engines must implement. This enables switching
between browser-use, Playwright, OpenBrowser, and others via a single
settings dropdown.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent


@dataclass
class BrowserResult:
    """Unified result from any browser backend."""
    success: bool
    content: str  # extracted text/data
    screenshot_path: Optional[str] = None
    urls_visited: list[str] = field(default_factory=list)
    is_done: bool = False
    error: Optional[str] = None


class BrowserBackend(ABC):
    """Base class for all browser backend adapters."""

    name: str = "base"
    display_name: str = "Base Backend"

    def __init__(self, agent: "Agent"):
        self.agent = agent

    @abstractmethod
    async def initialize(self) -> None:
        """Set up browser session / resources."""

    @abstractmethod
    async def run_task(self, task: str, max_steps: int = 25) -> BrowserResult:
        """Execute a browsing task. Returns unified BrowserResult."""

    @abstractmethod
    async def get_current_url(self) -> str:
        """Return current page URL."""

    @abstractmethod
    async def take_screenshot(self, path: str) -> None:
        """Save screenshot to path."""

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""

    @staticmethod
    def available_backends() -> dict[str, str]:
        """Return dict of {key: display_name} for all registered backends."""
        return {
            "browser_use": "Browser Use (Vision-based)",
            "playwright": "Playwright (Direct API)",
            "openbrowser": "OpenBrowser (CodeAgent)",
            "agent_browser": "Agent Browser (Vercel CLI)",
            "browserless": "Browserless (Docker Service)",
            "doppelganger": "Doppelganger (Self-hosted)",
            "lightpanda": "Lightpanda (Ultra-fast)",
        }
