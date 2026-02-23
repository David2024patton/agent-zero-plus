import asyncio
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers import files


class BrowserRead(Tool):
    """Lightweight page content extractor that reuses the existing browser session.
    
    Unlike browser_agent which spawns a full autonomous sub-agent, this tool
    directly reads page content from the current browser page with minimal
    overhead and no extra LLM calls.
    """

    async def execute(self, selector="", **kwargs):
        # Import browser_agent's State to reuse the existing browser session
        from python.tools.browser_agent import State

        state: State | None = self.agent.get_data("_browser_agent_state")

        if not state or not state.browser_session:
            return Response(
                message="No browser session is active. Use browser_agent first to open a page, then use browser_read to extract its content.",
                break_loop=False,
            )

        try:
            page = await state.get_page()
            if not page:
                return Response(
                    message="No page is currently open in the browser session. Use browser_agent to navigate to a page first.",
                    break_loop=False,
                )

            # Extract page metadata
            title = await page.title()
            url = page.url

            # Log the URL and title being read
            self.log.update(url=url, page_title=title)

            # Extract text content
            if selector and selector.strip():
                # Targeted extraction via CSS selector
                try:
                    element = await page.query_selector(selector.strip())
                    if element:
                        text = await element.inner_text()
                    else:
                        text = f"No element found matching selector: {selector}"
                except Exception as e:
                    text = f"Error querying selector '{selector}': {e}"
            else:
                # Full page text extraction
                text = await page.inner_text("body")

            # Truncate if extremely long (protect LLM context)
            max_chars = 15000
            truncated = False
            if len(text) > max_chars:
                text = text[:max_chars]
                truncated = True

            # Build response
            result_parts = [
                f"**Page Title**: {title}",
                f"**URL**: {url}",
                "",
                "**Content**:",
                text,
            ]
            if truncated:
                result_parts.append(
                    f"\n\n⚠️ Content truncated at {max_chars} characters. Use a CSS selector to target specific sections."
                )

            answer = "\n".join(result_parts)

        except Exception as e:
            PrintStyle().error(f"Error reading browser page: {e}")
            answer = f"Error reading browser page: {e}"

        self.log.update(content=answer[:500])  # truncate for log display
        return Response(message=answer, break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        kvps["model"] = f"{self.agent.config.chat_model.provider}/{self.agent.config.chat_model.name}"
        return self.agent.context.log.log(
            type="browser",
            heading=f"icon://article {self.agent.agent_name}: Reading Browser Page",
            content="",
            kvps=kvps,
        )

