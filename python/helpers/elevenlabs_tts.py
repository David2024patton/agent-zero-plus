"""
ElevenLabs TTS Helper for Agent Zero
=====================================
Provides text-to-speech synthesis using the ElevenLabs API.
Falls back to Kokoro if unavailable.
"""

import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger("agent-zero.elevenlabs")

# Check for httpx (async HTTP client)
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


async def synthesize(
    text: str,
    api_key: str = "",
    voice_id: str = "",
    model_id: str = "eleven_multilingual_v2",
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Synthesize speech from text using ElevenLabs API.

    Args:
        text: Text to convert to speech.
        api_key: ElevenLabs API key. Falls back to ELEVENLABS_API_KEY env var.
        voice_id: ElevenLabs voice ID.
        model_id: ElevenLabs model ID.
        output_path: Optional path to save the audio file.

    Returns:
        Audio bytes (mp3) or None on failure.
    """
    if not HAS_HTTPX:
        logger.error("httpx is not installed. Run: pip install httpx")
        return None

    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        logger.error("ElevenLabs API key not configured")
        return None

    if not voice_id:
        logger.error("ElevenLabs voice ID not configured")
        return None

    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            audio_bytes = response.content

            if output_path:
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
                logger.info(f"ElevenLabs audio saved to {output_path}")

            return audio_bytes

    except Exception as e:
        logger.error(f"ElevenLabs TTS failed: {e}")
        return None


async def stream_synthesize(
    text: str,
    api_key: str = "",
    voice_id: str = "",
    model_id: str = "eleven_multilingual_v2",
):
    """
    Stream synthesized speech from ElevenLabs API.

    Yields audio chunks as they arrive for real-time playback.
    """
    if not HAS_HTTPX:
        logger.error("httpx is not installed")
        return

    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key or not voice_id:
        logger.error("ElevenLabs API key or voice ID not configured")
        return

    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk
    except Exception as e:
        logger.error(f"ElevenLabs streaming TTS failed: {e}")


async def list_voices(api_key: str = "") -> list:
    """List available ElevenLabs voices."""
    if not HAS_HTTPX:
        return []

    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ELEVENLABS_API_BASE}/voices",
                headers={"xi-api-key": api_key},
            )
            response.raise_for_status()
            data = response.json()
            return [
                {"voice_id": v["voice_id"], "name": v["name"]}
                for v in data.get("voices", [])
            ]
    except Exception as e:
        logger.error(f"Failed to list ElevenLabs voices: {e}")
        return []
