import os
import asyncio
from python.helpers import dotenv, memory, perplexity_search, duckduckgo_search
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.errors import handle_error
from python.helpers.searxng import search as searxng

SEARCH_ENGINE_RESULTS = 20


class SearchEngine(Tool):
    async def execute(self, query="", **kwargs):
        count = int(self.args.get("count", SEARCH_ENGINE_RESULTS))
        categories = (self.args.get("categories") or "").strip()
        engines = (self.args.get("engines") or "").strip()

        searxng_result = await self.searxng_search(query, categories, engines, count)

        await self.agent.handle_intervention(
            searxng_result
        )  # wait for intervention and handle it, if paused

        return Response(message=searxng_result, break_loop=False)


    async def searxng_search(self, question, categories="", engines="", count=20):
        results = await searxng(question, categories=categories, engines=engines, count=count)
        return self.format_result_searxng(results, "Search Engine", count)

    def format_result_searxng(self, result, source, count=20):
        if isinstance(result, Exception):
            handle_error(result)
            return f"{source} search failed: {str(result)}"

        outputs = []
        for item in result["results"]:
            outputs.append(f"{item['title']}\n{item['url']}\n{item['content']}")

        return "\n\n".join(outputs[:count]).strip()
