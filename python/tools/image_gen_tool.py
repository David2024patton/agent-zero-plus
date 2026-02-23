"""
Agent Zero Tool: image_gen_tool
==================================
Generate images via OpenAI (DALL-E) or Google Gemini (Imagen).
Supports both providers — auto-detects based on available API keys.
"""

import os
import json
import base64
import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class ImageGenTool(Tool):

    async def execute(self, **kwargs) -> Response:
        method = (self.args.get("method") or "generate").strip().lower()
        prompt = (self.args.get("prompt") or "").strip()
        provider = (self.args.get("provider") or "").strip().lower()
        model = (self.args.get("model") or "").strip()
        size = (self.args.get("size") or "1024x1024").strip()
        quality = (self.args.get("quality") or "standard").strip()
        style = (self.args.get("style") or "vivid").strip()
        count = int(self.args.get("count", 1))
        save_path = (self.args.get("save_path") or "").strip()

        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

        # Determine provider
        if not provider:
            if openai_key:
                provider = "openai"
            elif gemini_key:
                provider = "gemini"
            else:
                return Response(
                    message="Error: No API key found. Set OPENAI_API_KEY or GEMINI_API_KEY.",
                    break_loop=False,
                )
        
        if provider == "gemini":
            if not gemini_key:
                return Response(
                    message="Error: GEMINI_API_KEY environment variable is required for Gemini provider.",
                    break_loop=False,
                )
            return await self._generate_gemini(gemini_key, prompt, model, save_path, count)
        else:
            if not openai_key:
                return Response(
                    message="Error: OPENAI_API_KEY environment variable is required for OpenAI provider.",
                    break_loop=False,
                )
            # Route to edit/variation methods (OpenAI only)
            if method == "edit":
                return await self._edit_image(openai_key)
            elif method == "variation":
                return await self._create_variation(openai_key)
            return await self._generate_openai(openai_key, prompt, model, size, quality, style, count, save_path)

    # ------------------------------------------------------------------
    # OpenAI DALL-E generation
    # ------------------------------------------------------------------

    async def _generate_openai(self, api_key: str, prompt: str, model: str,
                                size: str, quality: str, style: str,
                                count: int, save_path: str) -> Response:
        if not prompt:
            return Response(message="Error: 'prompt' is required.", break_loop=False)

        if not model:
            model = "dall-e-3"

        # DALL-E 3 only supports n=1
        if model == "dall-e-3":
            count = 1

        body: dict = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": count,
        }

        if model == "dall-e-3":
            body["quality"] = quality
            body["style"] = style

        if save_path:
            body["response_format"] = "b64_json"
        else:
            body["response_format"] = "url"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    data = await resp.json()

            if "error" in data:
                return Response(
                    message=f"OpenAI API Error: {data['error'].get('message', data['error'])}",
                    break_loop=False,
                )

            results = data.get("data", [])
            if not results:
                return Response(message="No images generated.", break_loop=False)

            lines = [f"**Generated {len(results)} image(s) via OpenAI DALL-E:**\n"]

            for i, img in enumerate(results):
                revised = img.get("revised_prompt", "")
                if save_path and "b64_json" in img:
                    ext = ".png"
                    fname = save_path if save_path.endswith(ext) else f"{save_path}_{i}{ext}"
                    img_bytes = base64.b64decode(img["b64_json"])
                    os.makedirs(os.path.dirname(fname) if os.path.dirname(fname) else ".", exist_ok=True)
                    with open(fname, "wb") as f:
                        f.write(img_bytes)
                    lines.append(f"- Saved to: `{fname}`")
                elif "url" in img:
                    lines.append(f"- URL: {img['url']}")

                if revised:
                    lines.append(f"  Revised prompt: {revised[:200]}")

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as e:
            PrintStyle().error(f"OpenAI image gen error: {e}")
            return Response(message=f"OpenAI image generation error: {e}", break_loop=False)

    # ------------------------------------------------------------------
    # Google Gemini Imagen generation
    # ------------------------------------------------------------------

    async def _generate_gemini(self, api_key: str, prompt: str, model: str,
                                save_path: str, count: int) -> Response:
        if not prompt:
            return Response(message="Error: 'prompt' is required.", break_loop=False)

        if not model:
            model = "gemini-2.0-flash-preview-image-generation"

        # Gemini Imagen API endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"]
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    data = await resp.json()

            if "error" in data:
                err_msg = data["error"].get("message", str(data["error"]))
                return Response(
                    message=f"Gemini API Error: {err_msg}",
                    break_loop=False,
                )

            # Parse Gemini response — images come as inline_data in parts
            candidates = data.get("candidates", [])
            if not candidates:
                return Response(message="No images generated by Gemini.", break_loop=False)

            lines = [f"**Generated image(s) via Google Gemini ({model}):**\n"]
            img_count = 0

            for candidate in candidates:
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                for part in parts:
                    # Text parts (descriptions)
                    if "text" in part:
                        lines.append(f"- Description: {part['text'][:200]}")
                    # Image parts (base64 inline data)
                    if "inlineData" in part:
                        inline = part["inlineData"]
                        mime_type = inline.get("mimeType", "image/png")
                        b64_data = inline.get("data", "")
                        if b64_data:
                            ext = ".png" if "png" in mime_type else ".jpg"
                            if save_path:
                                fname = save_path if save_path.endswith(ext) else f"{save_path}_{img_count}{ext}"
                            else:
                                fname = f"/tmp/gemini_image_{img_count}{ext}"
                            
                            img_bytes = base64.b64decode(b64_data)
                            os.makedirs(os.path.dirname(fname) if os.path.dirname(fname) else ".", exist_ok=True)
                            with open(fname, "wb") as f:
                                f.write(img_bytes)
                            lines.append(f"- Saved to: `{fname}`")
                            img_count += 1

            if img_count == 0:
                return Response(message="Gemini returned a response but no images were found.", break_loop=False)

            return Response(message="\n".join(lines), break_loop=False)

        except Exception as e:
            PrintStyle().error(f"Gemini image gen error: {e}")
            return Response(message=f"Gemini image generation error: {e}", break_loop=False)

    # ------------------------------------------------------------------
    # OpenAI Edit & Variation (unchanged)
    # ------------------------------------------------------------------

    async def _edit_image(self, api_key: str) -> Response:
        """Edit an image using DALL-E 2 with a prompt and optional mask."""
        image_path = (self.args.get("image_path") or "").strip()
        prompt = (self.args.get("prompt") or "").strip()
        mask_path = (self.args.get("mask_path") or "").strip()
        size = (self.args.get("size") or "1024x1024").strip()
        save_path = (self.args.get("save_path") or "").strip()

        if not image_path or not prompt:
            return Response(message="Error: 'image_path' and 'prompt' are required.", break_loop=False)
        if not os.path.exists(image_path):
            return Response(message=f"Error: Image not found: {image_path}", break_loop=False)

        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("image", open(image_path, "rb"), filename="image.png")
                data.add_field("prompt", prompt)
                data.add_field("size", size)
                data.add_field("n", "1")
                data.add_field("response_format", "b64_json" if save_path else "url")

                if mask_path and os.path.exists(mask_path):
                    data.add_field("mask", open(mask_path, "rb"), filename="mask.png")

                async with session.post(
                    "https://api.openai.com/v1/images/edits",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    result = await resp.json()

            if "error" in result:
                return Response(message=f"API Error: {result['error'].get('message', result['error'])}", break_loop=False)

            img = result.get("data", [{}])[0]
            if save_path and "b64_json" in img:
                img_bytes = base64.b64decode(img["b64_json"])
                os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(img_bytes)
                return Response(message=f"Edited image saved to `{save_path}`", break_loop=False)
            elif "url" in img:
                return Response(message=f"Edited image URL: {img['url']}", break_loop=False)
            return Response(message="No image returned.", break_loop=False)
        except Exception as e:
            return Response(message=f"Image edit error: {e}", break_loop=False)

    async def _create_variation(self, api_key: str) -> Response:
        """Generate variations of an existing image using DALL-E 2."""
        image_path = (self.args.get("image_path") or "").strip()
        size = (self.args.get("size") or "1024x1024").strip()
        count = int(self.args.get("count", 1))
        save_path = (self.args.get("save_path") or "").strip()

        if not image_path:
            return Response(message="Error: 'image_path' is required.", break_loop=False)
        if not os.path.exists(image_path):
            return Response(message=f"Error: Image not found: {image_path}", break_loop=False)

        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("image", open(image_path, "rb"), filename="image.png")
                data.add_field("size", size)
                data.add_field("n", str(count))
                data.add_field("response_format", "b64_json" if save_path else "url")

                async with session.post(
                    "https://api.openai.com/v1/images/variations",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as resp:
                    result = await resp.json()

            if "error" in result:
                return Response(message=f"API Error: {result['error'].get('message', result['error'])}", break_loop=False)

            images = result.get("data", [])
            lines = [f"**Generated {len(images)} variation(s):**\n"]
            for i, img in enumerate(images):
                if save_path and "b64_json" in img:
                    fname = f"{save_path}_{i}.png" if len(images) > 1 else save_path
                    img_bytes = base64.b64decode(img["b64_json"])
                    os.makedirs(os.path.dirname(fname) if os.path.dirname(fname) else ".", exist_ok=True)
                    with open(fname, "wb") as f:
                        f.write(img_bytes)
                    lines.append(f"- Saved to: `{fname}`")
                elif "url" in img:
                    lines.append(f"- URL: {img['url']}")
            return Response(message="\n".join(lines), break_loop=False)
        except Exception as e:
            return Response(message=f"Image variation error: {e}", break_loop=False)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://image {self.agent.agent_name}: Image Generation",
            content="",
            kvps=kvps,
        )
