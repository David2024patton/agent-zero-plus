"""
Agent Zero Tool: summarize_tool
===================================
Summarize URLs, local files, or YouTube videos using LLM APIs.
Uses OPENAI_API_KEY or GEMINI_API_KEY for summarization.
"""

import os
import asyncio
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class SummarizeTool(Tool):

    async def execute(self, **kwargs) -> Response:
        source = (self.args.get("source") or "").strip()
        method = (self.args.get("method") or "auto").strip().lower()
        style = (self.args.get("style") or "concise").strip()
        max_length = int(self.args.get("max_length", 500))

        if not source:
            return Response(message="Error: 'source' is required (URL, file path, or text).", break_loop=False)

        try:
            # Determine source type
            if source.startswith(("http://", "https://")):
                text = await self._fetch_url(source)
            elif os.path.exists(source):
                text = self._read_file(source)
            else:
                text = source  # Treat as raw text

            if not text or len(text.strip()) < 10:
                return Response(message="Error: Could not extract meaningful content from source.", break_loop=False)

            # Summarize using available LLM
            summary = await self._summarize(text, style, max_length)
            return Response(message=summary, break_loop=False)

        except Exception as e:
            PrintStyle().error(f"Summarize error: {e}")
            return Response(message=f"Summarization error: {e}", break_loop=False)

    async def _fetch_url(self, url: str) -> str:
        """Fetch content from a URL."""
        # For YouTube, try getting transcript first
        if "youtube.com" in url or "youtu.be" in url:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python", "-c",
                    f"""
from youtube_transcript_api import YouTubeTranscriptApi
url = "{url}"
vid = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]
transcript = YouTubeTranscriptApi.get_transcript(vid, languages=["en"])
print(" ".join(e["text"] for e in transcript))
""",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    return stdout.decode("utf-8", errors="replace").strip()
            except Exception:
                pass

        # Generic URL fetch
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                html = await resp.text()

        # Basic HTML stripping (try readability-style extraction)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Remove script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
        except ImportError:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:15000]

    def _read_file(self, path: str) -> str:
        """Read local file content."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:15000]

    async def _summarize(self, text: str, style: str, max_length: int) -> str:
        """Summarize text using available LLM API."""
        style_prompts = {
            "concise": f"Summarize the following in {max_length} words or fewer. Be clear and concise:",
            "detailed": f"Provide a detailed summary of the following in {max_length} words or fewer. Include key points, data, and conclusions:",
            "bullets": f"Summarize the following as bullet points ({max_length} words max). Use clear, actionable bullet points:",
            "eli5": f"Explain the following like I'm 5, in {max_length} words or fewer:",
            "technical": f"Provide a technical summary of the following in {max_length} words or fewer. Focus on architecture, implementation, and technical details:",
            "academic": f"Provide an academic summary of the following in {max_length} words or fewer. Include methodology, findings, significance, and limitations. Use formal academic style:",
        }
        system_prompt = style_prompts.get(style, style_prompts["concise"])

        # Try OpenAI first, then Gemini
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

        if openai_key:
            return await self._summarize_openai(text, system_prompt, openai_key)
        elif gemini_key:
            return await self._summarize_gemini(text, system_prompt, gemini_key)
        else:
            return f"Error: No LLM API key found. Set OPENAI_API_KEY or GEMINI_API_KEY.\n\nFirst 500 chars of content:\n{text[:500]}"

    async def _summarize_openai(self, text: str, system_prompt: str, api_key: str) -> str:
        body = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:12000]},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                data = await resp.json()

        if "error" in data:
            return f"OpenAI Error: {data['error'].get('message', data['error'])}"
        return data.get("choices", [{}])[0].get("message", {}).get("content", "(empty)")

    async def _summarize_gemini(self, text: str, system_prompt: str, api_key: str) -> str:
        body = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{text[:12000]}"}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                data = await resp.json()

        if "error" in data:
            return f"Gemini Error: {data['error'].get('message', data['error'])}"
        candidates = data.get("candidates", [])
        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "(empty)") if candidates else "(no response)"

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://summarize {self.agent.agent_name}: Summarize",
            content="",
            kvps=kvps,
        )
