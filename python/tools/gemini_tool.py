"""
Agent Zero Tool: gemini_tool
==============================
Call Google Gemini API for completions, vision analysis, and embeddings.
Requires GEMINI_API_KEY environment variable.
"""

import os
import json
import base64
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "generate").strip().lower()

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return Response(
                message="Error: GEMINI_API_KEY environment variable is required.",
                break_loop=False,
            )

        self._api_key = api_key

        methods = {
            "generate": self._generate,
            "vision": self._vision,
            "embed": self._embed,
            "list_models": self._list_models,
            "count_tokens": self._count_tokens,
        }

        if method not in methods:
            return Response(
                message=f"Error: invalid method '{method}'. Supported: {', '.join(methods.keys())}",
                break_loop=False,
            )

        try:
            return await methods[method]()
        except Exception as e:
            PrintStyle().error(f"Gemini tool error: {e}")
            return Response(message=f"Gemini error: {e}", break_loop=False)

    async def _generate(self) -> Response:
        prompt = (self.args.get("prompt") or "").strip()
        model = (self.args.get("model") or "gemini-2.0-flash").strip()
        system_instruction = (self.args.get("system_instruction") or "").strip()
        temperature = float(self.args.get("temperature", 0.7))
        max_tokens = int(self.args.get("max_tokens", 4096))

        if not prompt:
            return Response(message="Error: 'prompt' is required.", break_loop=False)

        body: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        url = f"{BASE_URL}/models/{model}:generateContent?key={self._api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()

        if "error" in data:
            return Response(message=f"API Error: {data['error'].get('message', data['error'])}", break_loop=False)

        candidates = data.get("candidates", [])
        if not candidates:
            return Response(message="No response generated.", break_loop=False)

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return Response(message=text or "(empty response)", break_loop=False)

    async def _vision(self) -> Response:
        prompt = (self.args.get("prompt") or "Describe this image.").strip()
        image_path = (self.args.get("image_path") or "").strip()
        image_url = (self.args.get("image_url") or "").strip()
        model = (self.args.get("model") or "gemini-2.0-flash").strip()

        parts: list = [{"text": prompt}]

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            ext = image_path.rsplit(".", 1)[-1].lower()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
            parts.append({"inline_data": {"mime_type": mime, "data": image_data}})
        elif image_url:
            parts.append({"file_data": {"file_uri": image_url}})
        else:
            return Response(message="Error: 'image_path' or 'image_url' is required.", break_loop=False)

        body = {"contents": [{"parts": parts}]}
        url = f"{BASE_URL}/models/{model}:generateContent?key={self._api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                data = await resp.json()

        if "error" in data:
            return Response(message=f"API Error: {data['error'].get('message', data['error'])}", break_loop=False)

        candidates = data.get("candidates", [])
        if not candidates:
            return Response(message="No vision response.", break_loop=False)

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return Response(message=text or "(empty response)", break_loop=False)

    async def _embed(self) -> Response:
        text = (self.args.get("text") or "").strip()
        model = (self.args.get("model") or "text-embedding-004").strip()

        if not text:
            return Response(message="Error: 'text' is required.", break_loop=False)

        body = {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
        url = f"{BASE_URL}/models/{model}:embedContent?key={self._api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()

        embedding = data.get("embedding", {}).get("values", [])
        return Response(
            message=f"Embedding ({len(embedding)} dimensions): [{', '.join(str(v)[:8] for v in embedding[:10])}{'...' if len(embedding) > 10 else ''}]",
            break_loop=False,
        )

    async def _list_models(self) -> Response:
        url = f"{BASE_URL}/models?key={self._api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()

        models = data.get("models", [])
        lines = [f"**Available Gemini Models ({len(models)}):**\n"]
        for m in models[:30]:
            name = m.get("name", "unknown").replace("models/", "")
            desc = m.get("description", "")[:80]
            lines.append(f"- **{name}**: {desc}")

        return Response(message="\n".join(lines), break_loop=False)

    async def _count_tokens(self) -> Response:
        text = (self.args.get("text") or "").strip()
        model = (self.args.get("model") or "gemini-2.0-flash").strip()

        if not text:
            return Response(message="Error: 'text' is required.", break_loop=False)

        body = {"contents": [{"parts": [{"text": text}]}]}
        url = f"{BASE_URL}/models/{model}:countTokens?key={self._api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()

        if "error" in data:
            return Response(message=f"API Error: {data['error'].get('message', data['error'])}", break_loop=False)

        total = data.get("totalTokens", "unknown")
        return Response(message=f"**Token count:** {total} tokens (model: {model})", break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        kvps.pop("image_path", None)
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://smart_toy {self.agent.agent_name}: Gemini AI",
            content="",
            kvps=kvps,
        )
