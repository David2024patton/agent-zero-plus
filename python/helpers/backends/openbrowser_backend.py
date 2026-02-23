"""
OpenBrowser CodeAgent backend adapter.

Uses the openbrowser-ai library which takes a code-first approach:
the LLM writes Python code that runs server-side against the browser
via CDP, returning only extracted results. This uses ~3.2x fewer tokens
than Playwright MCP and ~6x fewer than Chrome DevTools MCP.

Requires: pip install openbrowser-ai
"""

import asyncio
from typing import Optional, TYPE_CHECKING

from python.helpers.browser_backend import BrowserBackend, BrowserResult
from python.helpers.print_style import PrintStyle
from python.helpers import files

if TYPE_CHECKING:
    from agent import Agent


class OpenBrowserBackend(BrowserBackend):
    name = "openbrowser"
    display_name = "OpenBrowser (CodeAgent)"

    def __init__(self, agent: "Agent"):
        super().__init__(agent)
        self._ob_agent = None
        self._session = None

    async def initialize(self) -> None:
        if self._ob_agent:
            return
        try:
            from openbrowser import Agent as OBAgent, BrowserSession
        except ImportError:
            raise ImportError(
                "openbrowser-ai is not installed. Install with: pip install openbrowser-ai && openbrowser install"
            )

        # Get model config from agent
        model_config = self.agent.config.browser_model
        provider = model_config.provider
        model_name = model_config.name

        # Map Agent Zero provider names to OpenBrowser provider format
        provider_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "google",
            "gemini": "google",
            "groq": "groq",
            "ollama": "ollama",
            "openrouter": "openrouter",
        }

        ob_provider = provider_map.get(provider, provider)

        try:
            self._session = BrowserSession(headless=True)
            self._ob_agent = OBAgent(
                task="",  # will be set per run_task call
                browser_session=self._session,
                llm_provider=ob_provider,
                llm_model=model_name,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize OpenBrowser agent: {e}. "
                f"Provider: {ob_provider}, Model: {model_name}"
            ) from e

    async def run_task(self, task: str, max_steps: int = 25) -> BrowserResult:
        """Execute browser task using OpenBrowser's CodeAgent architecture."""
        try:
            await self.initialize()
        except Exception as e:
            return BrowserResult(
                success=False,
                content=f"OpenBrowser initialization failed: {str(e)}",
                is_done=True,
                error=str(e),
            )

        try:
            from openbrowser import Agent as OBAgent, BrowserSession

            # Create a fresh agent for this task (OpenBrowser agents are task-bound)
            self._ob_agent = OBAgent(
                task=task,
                browser_session=self._session,
                llm_provider=self._ob_agent._llm_provider if hasattr(self._ob_agent, '_llm_provider') else "openai",
                llm_model=self._ob_agent._llm_model if hasattr(self._ob_agent, '_llm_model') else "gpt-4o",
                max_steps=max_steps,
            )

            PrintStyle(font_color="#4fc3f7", padding=True).print(
                f"OpenBrowser backend executing task: {task}"
            )

            result = await asyncio.wait_for(
                self._ob_agent.run(), timeout=max_steps * 15  # ~15s per step max
            )

            # Extract result
            content = ""
            if result:
                if hasattr(result, "final_result"):
                    content = str(result.final_result())
                elif hasattr(result, "extracted_content"):
                    content = str(result.extracted_content)
                else:
                    content = str(result)

            # Get URLs if available
            urls = []
            if self._session:
                try:
                    page = await self._session.get_current_page()
                    if page:
                        urls = [page.url]
                except Exception:
                    pass

            # Take screenshot
            screenshot_path = None
            try:
                ss_dir = files.get_abs_path("tmp", "browser_screenshots")
                files.make_dirs(ss_dir)
                screenshot_path = files.get_abs_path(ss_dir, "openbrowser_latest.png")
                await self.take_screenshot(screenshot_path)
            except Exception:
                pass

            return BrowserResult(
                success=True,
                content=content or "Task completed successfully",
                screenshot_path=screenshot_path,
                urls_visited=urls,
                is_done=True,
            )

        except asyncio.TimeoutError:
            return BrowserResult(
                success=False,
                content=f"OpenBrowser task timed out after {max_steps * 15} seconds",
                is_done=True,
                error="timeout",
            )
        except Exception as e:
            return BrowserResult(
                success=False,
                content=f"OpenBrowser execution error: {str(e)}",
                is_done=True,
                error=str(e),
            )

    async def get_current_url(self) -> str:
        if self._session:
            try:
                page = await self._session.get_current_page()
                return page.url if page else ""
            except Exception:
                pass
        return ""

    async def take_screenshot(self, path: str) -> None:
        if self._session:
            try:
                page = await self._session.get_current_page()
                if page:
                    await page.screenshot(path=path, full_page=False)
            except Exception as e:
                PrintStyle().warning(f"OpenBrowser screenshot failed: {e}")

    async def close(self) -> None:
        try:
            if self._session:
                await self._session.close()
        except Exception as e:
            PrintStyle().warning(f"Error closing OpenBrowser backend: {e}")
        finally:
            self._ob_agent = None
            self._session = None
