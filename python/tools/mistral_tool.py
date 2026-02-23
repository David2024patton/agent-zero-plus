"""
Agent Zero Tool: mistral_tool
================================
Call Mistral AI API for chat completions and code generation.
Requires MISTRAL_API_KEY environment variable.
"""

import os
import json
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://api.mistral.ai/v1"


class MistralTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "chat").strip().lower()

        api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
        if not api_key:
            return Response(
                message="Error: MISTRAL_API_KEY environment variable is required.",
                break_loop=False,
            )

        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        methods = {
            "chat": self._chat,
            "codestral": self._codestral,
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
            PrintStyle().error(f"Mistral tool error: {e}")
            return Response(message=f"Mistral error: {e}", break_loop=False)

    async def _chat(self) -> Response:
        prompt = (self.args.get("prompt") or "").strip()
        model = (self.args.get("model") or "mistral-large-latest").strip()
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

    async def _codestral(self) -> Response:
        prompt = (self.args.get("prompt") or "").strip()
        suffix = (self.args.get("suffix") or "").strip()
        model = (self.args.get("model") or "codestral-latest").strip()
        temperature = float(self.args.get("temperature", 0.2))
        max_tokens = int(self.args.get("max_tokens", 4096))

        if not prompt:
            return Response(message="Error: 'prompt' is required.", break_loop=False)

        body: dict = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if suffix:
            body["suffix"] = suffix

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/fim/completions",
                headers=self._headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                data = await resp.json()

        if "error" in data:
            return Response(message=f"API Error: {data['error']}", break_loop=False)

        choices = data.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        return Response(message=text or "(empty)", break_loop=False)

    async def _embed(self) -> Response:
        text = (self.args.get("text") or "").strip()
        model = (self.args.get("model") or "mistral-embed").strip()

        if not text:
            return Response(message="Error: 'text' is required.", break_loop=False)

        body = {"model": model, "input": [text]}
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
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BASE_URL}/models",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()

        models = data.get("data", [])
        lines = [f"**Mistral Models ({len(models)}):**\n"]
        for m in models:
            lines.append(f"- **{m.get('id', 'unknown')}** (owned: {m.get('owned_by', '?')})")
        return Response(message="\n".join(lines), break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://smart_toy {self.agent.agent_name}: Mistral AI",
            content="",
            kvps=kvps,
        )
