"""
Matrix Channel Adapter for Agent Zero
=======================================
Uses matrix-nio to connect Agent Zero to Matrix/Element.
Supports room messages, DMs, and E2EE (if olm is installed).

Incorporates fixes from OpenClaw PRs:
  - #22359: Classify overloaded/503 errors as timeout → retry, not cooldown
  - #22355: Exponential backoff on reconnect (5s → 5min max)

Requires: pip install matrix-nio
"""

from __future__ import annotations
import os
import re
import asyncio
import logging
from typing import List, Optional

try:
    from nio import AsyncClient, RoomMessageText, MatrixRoom
    HAS_NIO = True
except ImportError:
    HAS_NIO = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage

logger = logging.getLogger("agent-zero.plugins.matrix")


# --- OpenClaw #22359: Overload error classification ---
_OVERLOAD_PATTERNS = re.compile(
    r"(overloaded|service.unavailable|high.demand|503|502|temporarily.unavailable)",
    re.IGNORECASE,
)


def _is_overload_error(error: Exception) -> bool:
    """Classify overloaded/service-unavailable as transient timeout, not rate limit."""
    return bool(_OVERLOAD_PATTERNS.search(str(error)))


class MatrixChannelAdapter(ChannelAdapter):
    """
    Matrix channel adapter using matrix-nio.
    Listens for messages in joined rooms and DMs.
    Includes overload retry (#22359) and reconnect backoff (#22355).
    """

    # Retry config (OpenClaw #22359)
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2.0

    # Reconnect config (OpenClaw #22355)
    RECONNECT_INITIAL_DELAY = 5.0
    RECONNECT_MAX_DELAY = 300.0  # 5 minutes

    def __init__(
        self,
        homeserver_url: str = "https://matrix.org",
        user_id: str = "",
        access_token_env: str = "MATRIX_ACCESS_TOKEN",
        allowed_rooms: str = "",
        respond_to_dms: bool = True,
    ):
        super().__init__(channel_id="matrix")
        self.homeserver_url = homeserver_url
        self.user_id = user_id
        self.access_token_env = access_token_env
        self.allowed_rooms = [r.strip() for r in allowed_rooms.split(",") if r.strip()] if allowed_rooms else []
        self.respond_to_dms = respond_to_dms
        self._client: Optional[AsyncClient] = None
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
        self._should_reconnect = True
        self._sync_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the Matrix client."""
        if not HAS_NIO:
            logger.error("matrix-nio is not installed. Run: pip install matrix-nio")
            return

        access_token = os.environ.get(self.access_token_env)
        if not access_token:
            logger.error(f"Matrix access token not found in env var: {self.access_token_env}")
            return

        if not self.user_id:
            logger.error("Matrix user_id not configured")
            return

        self._client = AsyncClient(self.homeserver_url, self.user_id)
        self._client.access_token = access_token

        # Register message callback
        self._client.add_event_callback(self._handle_message, RoomMessageText)

        logger.info(f"Starting Matrix client as {self.user_id}...")
        # Perform initial sync then start syncing with reconnect wrapper
        await self._client.sync(timeout=10000)
        # OpenClaw #22355: Run sync_forever with reconnect wrapper
        self._sync_task = asyncio.create_task(self._sync_with_reconnect())

    async def _sync_with_reconnect(self):
        """OpenClaw #22355: Run sync_forever with auto-reconnect on failure."""
        while self._should_reconnect:
            try:
                await self._client.sync_forever(timeout=30000)
                # sync_forever returned normally (shouldn't happen unless stopped)
                if not self._should_reconnect:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._should_reconnect:
                    break
                logger.warning(
                    f"Matrix sync disconnected ({e}). "
                    f"Reconnecting in {self._reconnect_delay:.0f}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self.RECONNECT_MAX_DELAY
                )

        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY

    async def stop(self):
        """Stop the Matrix client gracefully."""
        self._should_reconnect = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.close()
            logger.info("Matrix client disconnected")

    async def _handle_message(self, room: MatrixRoom, event: RoomMessageText):
        """Handle incoming Matrix messages."""
        # Don't respond to our own messages
        if event.sender == self.user_id:
            return

        # Check allowed rooms
        if self.allowed_rooms and room.room_id not in self.allowed_rooms:
            return

        # DM detection (rooms with exactly 2 members)
        is_dm = room.member_count == 2
        if is_dm and not self.respond_to_dms:
            return

        channel_msg = ChannelMessage(
            channel_id="matrix",
            sender_id=event.sender,
            sender_name=room.user_name(event.sender) or event.sender,
            content=event.body,
            metadata={
                "room_id": room.room_id,
                "room_name": room.display_name,
                "event_id": event.event_id,
                "is_dm": is_dm,
            },
        )

        await self._dispatch_message(channel_msg)

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send a message to a Matrix room.

        'to' format: "room:<room_id>" (e.g. "room:!abc123:matrix.org")
        """
        if not self._client:
            logger.error("Matrix client not connected")
            return False

        try:
            _, room_id = to.split(":", 1)
            # Re-join the room_id since it contains colons (e.g. !abc:matrix.org)
            room_id = ":" .join(to.split(":")[1:])
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'room:<room_id>'")
            return False

        # OpenClaw #22359: Retry on overload with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                chunks = self._split_message(content, max_length=65535)
                for chunk in chunks:
                    await self._client.room_send(
                        room_id=room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.text",
                            "body": chunk,
                        },
                    )
                return True
            except Exception as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Matrix API overloaded (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to send Matrix message: {e}")
                    return False
        return False

    @staticmethod
    def _split_message(content: str, max_length: int = 65535) -> List[str]:
        """Split a long message into chunks."""
        if len(content) <= max_length:
            return [content]
        chunks = []
        while content:
            if len(content) <= max_length:
                chunks.append(content)
                break
            split_at = content.rfind("\n", 0, max_length)
            if split_at == -1:
                split_at = content.rfind(" ", 0, max_length)
            if split_at == -1:
                split_at = max_length
            chunks.append(content[:split_at])
            content = content[split_at:].lstrip()
        return chunks
