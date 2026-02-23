"""
Playwright direct-API backend adapter.

Uses Playwright directly for deterministic, fast browser automation
without LLM overhead per step. The LLM writes the task description,
and this adapter translates it into Playwright API calls.
"""

import asyncio
from typing import Optional, TYPE_CHECKING

from python.helpers.browser_backend import BrowserBackend, BrowserResult
from python.helpers.print_style import PrintStyle
from python.helpers import files

if TYPE_CHECKING:
    from agent import Agent


class PlaywrightBackend(BrowserBackend):
    name = "playwright"
    display_name = "Playwright (Direct API)"

    def __init__(self, agent: "Agent"):
        super().__init__(agent)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def initialize(self) -> None:
        if self._page:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()

    async def run_task(self, task: str, max_steps: int = 25) -> BrowserResult:
        """
        Execute browser task using Playwright.

        For Playwright, the 'task' is interpreted as a set of natural-language
        instructions. We use the agent's utility model to generate Playwright
        code from the task description, then execute it.
        """
        await self.initialize()

        system_prompt = """You are a browser automation assistant. Given a task description,
generate Python code using Playwright to accomplish it. The code will be executed in an
async context where these variables are available:
- `page`: the current Playwright page object
- `context`: the browser context (for multi-tab operations)

Rules:
- Use `await` for all Playwright calls
- For multi-tab: use `context.new_page()` to open new tabs
- Use `context.pages` to list all open tabs
- Always collect results into a variable called `result` (a string)
- Handle errors gracefully with try/except
- Do NOT import anything or create new browser instances
- Do NOT call `browser.close()` or `context.close()`
- Keep code concise and focused on the task

Output ONLY the Python code, no markdown fences, no explanation."""

        try:
            # Ask the utility model to generate Playwright code from the task
            code = await self.agent.call_utility_model(
                system=system_prompt,
                message=f"Task: {task}",
            )

            # Clean up code (remove markdown fences if present)
            code = code.strip()
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:])
            if code.endswith("```"):
                code = code[:-3].strip()

            PrintStyle(font_color="#4fc3f7", padding=True).print(
                f"Playwright backend executing generated code:\n{code}"
            )

            # Execute the generated code
            local_vars = {
                "page": self._page,
                "context": self._context,
                "result": "",
                "asyncio": asyncio,
            }

            exec(
                f"async def _pw_task():\n"
                + "\n".join(f"    {line}" for line in code.split("\n"))
                + "\n    return result if 'result' in dir() else 'Task completed'",
                {"__builtins__": __builtins__},
                local_vars,
            )

            result_text = await asyncio.wait_for(
                local_vars["_pw_task"](), timeout=60
            )

            # Collect URLs
            urls = [p.url for p in self._context.pages if not p.is_closed()]

            # Take screenshot
            screenshot_path = None
            try:
                ss_dir = files.get_abs_path("tmp", "browser_screenshots")
                files.make_dirs(ss_dir)
                screenshot_path = files.get_abs_path(ss_dir, "playwright_latest.png")
                await self._page.screenshot(path=screenshot_path, full_page=False)
            except Exception:
                pass

            return BrowserResult(
                success=True,
                content=str(result_text) if result_text else "Task completed successfully",
                screenshot_path=screenshot_path,
                urls_visited=urls,
                is_done=True,
            )

        except asyncio.TimeoutError:
            return BrowserResult(
                success=False,
                content="Playwright task timed out after 60 seconds",
                is_done=True,
                error="timeout",
            )
        except Exception as e:
            return BrowserResult(
                success=False,
                content=f"Playwright execution error: {str(e)}",
                is_done=True,
                error=str(e),
            )

    async def get_current_url(self) -> str:
        if self._page and not self._page.is_closed():
            return self._page.url
        return ""

    async def take_screenshot(self, path: str) -> None:
        if self._page and not self._page.is_closed():
            await self._page.screenshot(path=path, full_page=False)

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            PrintStyle().warning(f"Error closing Playwright backend: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
