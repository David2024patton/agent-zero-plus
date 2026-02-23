"""
Agent Zero Tool: zai_tool
============================
Call Zhipu AI (Z.AI) API for chat completions.
Requires Z_AI_API_KEY environment variable.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


class ZAITool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "chat").strip().lower()

        api_key = os.environ.get("Z_AI_API_KEY", "").strip()
        if not api_key:
            return Response(
                message="Error: Z_AI_API_KEY environment variable is required.",
                break_loop=False,
            )

        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        methods = {
            "chat": self._chat,
            "embed": self._embed,
            "list_models": self._list_models,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"Z.AI tool error: {e}")
            return Response(message=f"Z.AI error: {e}", break_loop=False)

    async def _chat(self) -> Response:
        prompt = (self.args.get("prompt") or "").strip()
        model = (self.args.get("model") or "glm-4-plus").strip()
        system = (self.args.get("system") or "").strip()
        temperature = float(self.args.get("temperature", 0.7))
        max_tokens = int(self.args.get("max_tokens", 4096))

        if not prompt:
            return Response(message="Error: 'prompt' is required.", break_loop=False)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/chat/completions",
                headers=self._headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                data = await resp.json()

        if "error" in data:
            return Response(message=f"API Error: {data['error']}", break_loop=False)

        choices = data.get("choices", [])
        if not choices:
            return Response(message="No response generated.", break_loop=False)

        text = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        footer = f"\n\n*Tokens: {usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out*"
        return Response(message=(text or "(empty)") + footer, break_loop=False)

    async def _embed(self) -> Response:
        text = (self.args.get("text") or "").strip()
        model = (self.args.get("model") or "embedding-3").strip()

        if not text:
            return Response(message="Error: 'text' is required.", break_loop=False)

        body = {"model": model, "input": text}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/embeddings",
                headers=self._headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                data = await resp.json()

        embeddings = data.get("data", [])
        if not embeddings:
            return Response(message="No embedding returned.", break_loop=False)

        vec = embeddings[0].get("embedding", [])
        return Response(
            message=f"Embedding ({len(vec)} dimensions): [{', '.join(str(v)[:8] for v in vec[:10])}...]",
            break_loop=False,
        )

    async def _list_models(self) -> Response:
        models = [
            "glm-4-plus — Most capable GLM model",
            "glm-4-long — 128K context window",
            "glm-4-flash — Fast and efficient",
            "glm-4v-plus — Vision + Language",
            "glm-4v — Vision model",
            "embedding-3 — Text embeddings",
            "cogview-3-plus — Image generation",
        ]
        lines = ["**Z.AI Available Models:**\n"] + [f"- **{m}**" for m in models]
        return Response(message="\n".join(lines), break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://smart_toy {self.agent.agent_name}: Z.AI",
            content="",
            kvps=kvps,
        )
