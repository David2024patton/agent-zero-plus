"""
Agent Zero Tool: whisper_tool
================================
Transcribe audio files using the OpenAI Whisper API.
Requires OPENAI_API_KEY environment variable.
"""

import os
import asyncio
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class WhisperTool(Tool):

    async def execute(self, **kwargs) -> Response:
        file_path = (self.args.get("file_path") or "").strip()
        model = (self.args.get("model") or "whisper-1").strip()
        language = (self.args.get("language") or "").strip()
        response_format = (self.args.get("format") or "text").strip()
        prompt_hint = (self.args.get("prompt") or "").strip()
        method = (self.args.get("method") or "transcribe").strip().lower()

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return Response(
                message="Error: OPENAI_API_KEY environment variable is required.",
                break_loop=False,
            )

        if not file_path:
            return Response(message="Error: 'file_path' is required.", break_loop=False)

        if not os.path.exists(file_path):
            return Response(message=f"Error: File not found: {file_path}", break_loop=False)

        # Check file size (max 25MB for Whisper API)
        file_size = os.path.getsize(file_path)
        if file_size > 25 * 1024 * 1024:
            return Response(
                message=f"Error: File too large ({file_size / 1024 / 1024:.1f}MB). Max is 25MB.",
                break_loop=False,
            )

        endpoint = "translations" if method == "translate" else "transcriptions"

        file_handle = None
        try:
            file_handle = open(file_path, "rb")
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", file_handle, filename=os.path.basename(file_path))
                data.add_field("model", model)
                data.add_field("response_format", response_format)

                if language and method != "translate":
                    data.add_field("language", language)
                if prompt_hint:
                    data.add_field("prompt", prompt_hint)

                async with session.post(
                    f"https://api.openai.com/v1/audio/{endpoint}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if response_format in ("json", "verbose_json"):
                        result = await resp.json()
                        text = result.get("text", str(result))
                    else:
                        text = await resp.text()

            if not text.strip():
                return Response(message="Transcription returned empty result.", break_loop=False)

            # If there's a save path, save the transcription
            save_path = (self.args.get("save_path") or "").strip()
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(text)
                return Response(
                    message=f"Transcription saved to `{save_path}` ({len(text)} chars):\n\n{text[:2000]}",
                    break_loop=False,
                )

            return Response(message=text[:5000], break_loop=False)

        except Exception as e:
            PrintStyle().error(f"Whisper tool error: {e}")
            return Response(message=f"Transcription error: {e}", break_loop=False)
        finally:
            if file_handle and not file_handle.closed:
                file_handle.close()

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://mic {self.agent.agent_name}: Audio Transcription",
            content="",
            kvps=kvps,
        )
