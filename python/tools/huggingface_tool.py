"""
Agent Zero Tool: huggingface_tool
====================================
Interact with HuggingFace Hub for inference, model info, and dataset management.
Requires HUGGINGFACE_TOKEN environment variable.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


INFERENCE_URL = "https://api-inference.huggingface.co/models"
API_URL = "https://huggingface.co/api"


class HuggingFaceTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "").strip().lower()

        token = os.environ.get("HUGGINGFACE_TOKEN", "").strip()
        if not token:
            return Response(
                message="Error: HUGGINGFACE_TOKEN environment variable is required.",
                break_loop=False,
            )

        self._headers = {"Authorization": f"Bearer {token}"}

        methods = {
            "inference": self._inference,
            "model_info": self._model_info,
            "search_models": self._search_models,
            "search_datasets": self._search_datasets,
            "whoami": self._whoami,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"HuggingFace tool error: {e}")
            return Response(message=f"HuggingFace error: {e}", break_loop=False)

    async def _inference(self) -> Response:
        model = (self.args.get("model") or "").strip()
        inputs = (self.args.get("inputs") or "").strip()
        task = (self.args.get("task") or "text-generation").strip()

        if not model or not inputs:
            return Response(message="Error: 'model' and 'inputs' are required.", break_loop=False)

        body: dict = {"inputs": inputs}
        params = {}
        max_tokens = self.args.get("max_tokens")
        temperature = self.args.get("temperature")
        if max_tokens:
            params["max_new_tokens"] = int(max_tokens)
        if temperature:
            params["temperature"] = float(temperature)
        if params:
            body["parameters"] = params

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{INFERENCE_URL}/{model}",
                headers={**self._headers, "Content-Type": "application/json"},
                json=body,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.content_type == "application/json":
                    data = await resp.json()
                else:
                    # Binary response (images, audio)
                    content = await resp.read()
                    return Response(
                        message=f"Binary output received ({len(content)} bytes). Save with code_execution_tool.",
                        break_loop=False,
                    )

        if isinstance(data, dict) and "error" in data:
            return Response(message=f"API Error: {data['error']}", break_loop=False)

        # Handle different response formats
        if isinstance(data, list):
            if data and isinstance(data[0], dict):
                text = data[0].get("generated_text", data[0].get("summary_text", json.dumps(data[0])))
            else:
                text = json.dumps(data)
        else:
            text = json.dumps(data, indent=2)

        return Response(message=text[:5000], break_loop=False)

    async def _model_info(self) -> Response:
        model = (self.args.get("model") or "").strip()
        if not model:
            return Response(message="Error: 'model' is required.", break_loop=False)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/models/{model}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        lines = [
            f"**{data.get('modelId', model)}**",
            f"- Pipeline: {data.get('pipeline_tag', 'N/A')}",
            f"- Downloads: {data.get('downloads', 'N/A')}",
            f"- Likes: {data.get('likes', 'N/A')}",
            f"- Library: {data.get('library_name', 'N/A')}",
            f"- Tags: {', '.join(data.get('tags', [])[:10])}",
        ]
        return Response(message="\n".join(lines), break_loop=False)

    async def _search_models(self) -> Response:
        query = (self.args.get("query") or "").strip()
        limit = int(self.args.get("limit", 10))

        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/models",
                params={"search": query, "limit": limit, "sort": "downloads", "direction": -1},
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        if not data:
            return Response(message="No models found.", break_loop=False)

        lines = [f"**Models matching '{query}' ({len(data)}):**\n"]
        for m in data:
            dl = m.get("downloads", 0)
            lines.append(f"- **{m.get('modelId', '?')}** ({m.get('pipeline_tag', '?')}) — {dl:,} downloads")
        return Response(message="\n".join(lines), break_loop=False)

    async def _search_datasets(self) -> Response:
        query = (self.args.get("query") or "").strip()
        limit = int(self.args.get("limit", 10))

        if not query:
            return Response(message="Error: 'query' is required.", break_loop=False)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/datasets",
                params={"search": query, "limit": limit, "sort": "downloads", "direction": -1},
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        if not data:
            return Response(message="No datasets found.", break_loop=False)

        lines = [f"**Datasets matching '{query}' ({len(data)}):**\n"]
        for d in data:
            dl = d.get("downloads", 0)
            lines.append(f"- **{d.get('id', '?')}** — {dl:,} downloads")
        return Response(message="\n".join(lines), break_loop=False)

    async def _whoami(self) -> Response:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://huggingface.co/api/whoami-v2",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        return Response(
            message=f"Logged in as **{data.get('name', 'unknown')}** (type: {data.get('type', '?')})",
            break_loop=False,
        )

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://hub {self.agent.agent_name}: HuggingFace",
            content="",
            kvps=kvps,
        )
