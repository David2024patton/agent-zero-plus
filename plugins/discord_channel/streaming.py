"""
Discord Streaming Preview
=========================
Adapts Agent Zero's StreamingReply to Discord's message editing API.

Modes:
  - "off"     — No streaming, send complete messages only
  - "partial" — Edit a single message in-place as tokens arrive
  - "block"   — Chunked drafts, create new messages at paragraph breaks

Respects Discord's constraints:
  - 2000 character limit per message
  - Rate limit awareness (~5 edits/sec global, throttled to 0.5s)
  - Graceful split on natural break points
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, List, Optional

logger = logging.getLogger("agent-zero.plugins.discord.streaming")

# Discord limits
MAX_MESSAGE_LENGTH = 2000
EDIT_THROTTLE_SECONDS = 0.5
TYPING_INDICATOR = "▍"


class DiscordStreamingReply:
    """
    Manages a streaming response in Discord by editing a message in-place.

    In 'partial' mode:
      - Sends an initial placeholder message
      - Edits it with accumulated tokens at throttled intervals
      - On completion, sends the final clean text

    In 'block' mode:
      - Accumulates tokens until a paragraph break or chunk threshold
      - Sends each chunk as a new message
      - Better for long responses that would exceed 2000 chars
    """

    def __init__(
        self,
        channel,          # discord.TextChannel or Thread
        mode: str = "off",
        min_chunk_chars: int = 200,
        max_chunk_chars: int = 800,
        break_preference: str = "paragraph",  # paragraph, sentence, word
    ):
        self._channel = channel
        self._mode = mode
        self._min_chunk = min_chunk_chars
        self._max_chunk = max_chunk_chars
        self._break_pref = break_preference

        # State
        self._message = None       # The Discord message being edited
        self._buffer: str = ""     # Accumulated text
        self._sent_length: int = 0 # How much of buffer has been sent/edited
        self._last_edit: float = 0
        self._finished: bool = False
        self._messages_sent: List[Any] = []  # All messages sent (for block mode)

    @property
    def is_streaming(self) -> bool:
        return self._mode != "off" and not self._finished

    @property
    def mode(self) -> str:
        return self._mode

    async def start(self):
        """Initialize the streaming message."""
        if self._mode == "off":
            return

        if self._mode == "partial":
            try:
                self._message = await self._channel.send(TYPING_INDICATOR)
                self._messages_sent.append(self._message)
            except Exception as e:
                logger.error(f"Failed to send initial streaming message: {e}")
                self._mode = "off"  # Fallback to non-streaming

    async def append(self, text: str):
        """
        Append new tokens to the stream.

        In partial mode: edits the message when throttle allows.
        In block mode: accumulates and sends chunks at break points.
        """
        if self._mode == "off" or self._finished:
            return

        self._buffer += text

        if self._mode == "partial":
            await self._update_partial()
        elif self._mode == "block":
            await self._flush_blocks()

    async def finish(self) -> str:
        """
        Finalize the stream. Returns the complete text.

        In partial mode: final edit removes typing indicator.
        In block mode: sends any remaining buffered text.
        """
        self._finished = True

        if self._mode == "partial" and self._message and self._buffer:
            # Final edit with clean text (no indicator)
            display = self._truncate(self._buffer)
            try:
                await self._message.edit(content=display)
            except Exception as e:
                logger.debug(f"Final stream edit failed: {e}")
                # Send overflow if truncated
                if len(self._buffer) > MAX_MESSAGE_LENGTH:
                    await self._send_overflow(self._buffer[MAX_MESSAGE_LENGTH:])

        elif self._mode == "block" and self._buffer[self._sent_length:]:
            # Send remaining buffer
            remaining = self._buffer[self._sent_length:]
            if remaining.strip():
                try:
                    msg = await self._channel.send(remaining[:MAX_MESSAGE_LENGTH])
                    self._messages_sent.append(msg)
                except Exception as e:
                    logger.debug(f"Final block send failed: {e}")

        return self._buffer

    # ─── Internal: partial mode ───

    async def _update_partial(self):
        """Edit the streaming message with current buffer."""
        now = time.time()
        if now - self._last_edit < EDIT_THROTTLE_SECONDS:
            return  # Rate limited

        if not self._message:
            return

        display = self._truncate(self._buffer + TYPING_INDICATOR)
        try:
            await self._message.edit(content=display)
            self._last_edit = now
        except Exception as e:
            logger.debug(f"Stream edit throttled or failed: {e}")

    # ─── Internal: block mode ───

    async def _flush_blocks(self):
        """Send complete chunks in block mode."""
        unsent = self._buffer[self._sent_length:]

        if len(unsent) < self._min_chunk:
            return  # Not enough to send

        # Find a good break point
        break_pos = self._find_break(unsent)
        if break_pos is None or break_pos < self._min_chunk:
            if len(unsent) >= self._max_chunk:
                break_pos = self._max_chunk
            else:
                return  # Wait for more text

        chunk = unsent[:break_pos]
        if not chunk.strip():
            return

        try:
            msg = await self._channel.send(chunk[:MAX_MESSAGE_LENGTH])
            self._messages_sent.append(msg)
            self._sent_length += break_pos
        except Exception as e:
            logger.debug(f"Block send failed: {e}")

    def _find_break(self, text: str) -> Optional[int]:
        """Find good break point based on preference."""
        if self._break_pref == "paragraph":
            # Look for double newline
            idx = text.find("\n\n")
            if idx > 0:
                return idx + 2
        if self._break_pref in ("paragraph", "sentence"):
            # Look for sentence end
            for end in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
                idx = text.rfind(end, 0, self._max_chunk)
                if idx > 0:
                    return idx + len(end)
        if self._break_pref in ("paragraph", "sentence", "word"):
            # Look for word break
            idx = text.rfind(" ", 0, self._max_chunk)
            if idx > 0:
                return idx + 1
        return None

    # ─── Helpers ───

    def _truncate(self, text: str) -> str:
        """Truncate text to Discord's message limit."""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return text
        return text[:MAX_MESSAGE_LENGTH - 3] + "..."

    async def _send_overflow(self, text: str):
        """Send overflow text as additional messages."""
        while text:
            chunk = text[:MAX_MESSAGE_LENGTH]
            text = text[MAX_MESSAGE_LENGTH:]
            try:
                msg = await self._channel.send(chunk)
                self._messages_sent.append(msg)
            except Exception as e:
                logger.error(f"Overflow send failed: {e}")
                break

    @property
    def message_count(self) -> int:
        return len(self._messages_sent)

    @property
    def content(self) -> str:
        return self._buffer
