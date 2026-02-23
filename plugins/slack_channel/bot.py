"""
Slack Channel Adapter for Agent Zero
======================================
Uses slack-bolt (Socket Mode) to connect Agent Zero to Slack.
Supports DMs, @mentions, and channel messages.

Incorporates fixes from OpenClaw PRs:
  - #22359: Classify overloaded/503 errors as timeout → retry, not cooldown
  - #22355: Exponential backoff on reconnect (5s → 5min max)

Requires: pip install slack-bolt
"""

from __future__ import annotations
import os
import re
import asyncio
import logging
from typing import List, Optional

try:
    from slack_bolt.async_app import AsyncApp
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    HAS_SLACK = True
except ImportError:
    HAS_SLACK = False

from python.helpers.plugin_api import ChannelAdapter, ChannelMessage
from python.helpers.lifecycle_reactions import (
    LifecycleTracker, check_dm_access, get_model_override,
)

logger = logging.getLogger("agent-zero.plugins.slack")


# --- OpenClaw #22359: Overload error classification ---
_OVERLOAD_PATTERNS = re.compile(
    r"(overloaded|service.unavailable|high.demand|503|502|temporarily.unavailable)",
    re.IGNORECASE,
)


def _is_overload_error(error: Exception) -> bool:
    """Classify overloaded/service-unavailable as transient timeout, not rate limit."""
    return bool(_OVERLOAD_PATTERNS.search(str(error)))


class SlackChannelAdapter(ChannelAdapter):
    """
    Slack channel adapter.
    Uses Socket Mode for real-time event handling without a public endpoint.
    Includes overload retry logic (OpenClaw #22359) and reconnect backoff (#22355).
    """

    # Retry config (OpenClaw #22359)
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2.0

    # Reconnect config (OpenClaw #22355)
    RECONNECT_INITIAL_DELAY = 5.0
    RECONNECT_MAX_DELAY = 300.0  # 5 minutes

    def __init__(
        self,
        bot_token_env: str = "SLACK_BOT_TOKEN",
        app_token_env: str = "SLACK_APP_TOKEN",
        signing_secret_env: str = "SLACK_SIGNING_SECRET",
        allowed_channels: str = "",
        respond_to_dms: bool = True,
        respond_to_mentions: bool = True,
    ):
        super().__init__(channel_id="slack")
        self.bot_token_env = bot_token_env
        self.app_token_env = app_token_env
        self.signing_secret_env = signing_secret_env
        self.allowed_channels = [c.strip() for c in allowed_channels.split(",") if c.strip()] if allowed_channels else []
        self.respond_to_dms = respond_to_dms
        self.respond_to_mentions = respond_to_mentions
        self._app = None
        self._handler = None
        self._bot_user_id: Optional[str] = None
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
        self._should_reconnect = True
        self._reconnect_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the Slack bot via Socket Mode."""
        if not HAS_SLACK:
            logger.error("slack-bolt is not installed. Run: pip install slack-bolt")
            return

        bot_token = os.environ.get(self.bot_token_env)
        app_token = os.environ.get(self.app_token_env)
        if not bot_token:
            logger.error(f"Slack bot token not found in env var: {self.bot_token_env}")
            return
        if not app_token:
            logger.error(f"Slack app token not found in env var: {self.app_token_env}")
            return

        self._app = AsyncApp(token=bot_token)

        # Get bot user ID for mention detection
        auth_response = await self._app.client.auth_test()
        self._bot_user_id = auth_response.get("user_id")

        @self._app.event("message")
        async def handle_message(event, say):
            await self._handle_message(event, say)

        @self._app.event("app_mention")
        async def handle_mention(event, say):
            await self._handle_message(event, say, is_mention=True)

        self._handler = AsyncSocketModeHandler(self._app, app_token)
        logger.info("Starting Slack bot (Socket Mode)...")
        await self._handler.start_async()

        # OpenClaw #22355: Start reconnect monitor
        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """OpenClaw #22355: Auto-reconnect with exponential backoff on disconnect."""
        while self._should_reconnect:
            try:
                if self._handler and hasattr(self._handler, 'client') and self._handler.client:
                    if self._handler.client.is_connected():
                        await asyncio.sleep(10)
                        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
                        continue

                if not self._should_reconnect:
                    break

                logger.warning(
                    f"Slack connection lost. Reconnecting in {self._reconnect_delay:.0f}s..."
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self.RECONNECT_MAX_DELAY
                )

                try:
                    if self._handler:
                        await self._handler.connect_async()
                        self._reconnect_delay = self.RECONNECT_INITIAL_DELAY
                        logger.info("Slack reconnected successfully")
                except Exception as e:
                    logger.error(f"Slack reconnect failed: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnect loop error: {e}")
                await asyncio.sleep(self._reconnect_delay)

    async def stop(self):
        """Stop the Slack bot gracefully."""
        self._should_reconnect = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._handler:
            await self._handler.close_async()
            logger.info("Slack bot disconnected")

    async def _handle_message(self, event: dict, say, is_mention: bool = False):
        """Handle incoming Slack messages with lifecycle tracking."""
        # Skip bot messages
        if event.get("bot_id") or event.get("subtype"):
            return

        user = event.get("user", "")
        channel = event.get("channel", "")
        text = event.get("text", "").strip()
        channel_type = event.get("channel_type", "")
        ts = event.get("ts", "")

        if not text:
            return

        # DM check with access control
        if channel_type == "im":
            if not self.respond_to_dms:
                return
            if not check_dm_access("slack", user):
                return
        elif is_mention:
            if not self.respond_to_mentions:
                return
            # Remove mention from text
            if self._bot_user_id:
                text = text.replace(f"<@{self._bot_user_id}>", "").strip()
        else:
            return  # Only respond to DMs and mentions

        # Check allowed channels
        if self.allowed_channels and channel not in self.allowed_channels:
            return

        # --- Lifecycle reactions via Slack API ---
        msg_ref = {"channel": channel, "ts": ts}

        async def _react(ref, emoji):
            emoji_name = {
                "📨": "incoming_envelope",
                "🤔": "thinking_face",
                "⚙️": "gear",
                "✅": "white_check_mark",
                "❌": "x",
                "💬": "speech_balloon",
            }.get(emoji, "robot_face")
            try:
                await self._app.client.reactions_add(
                    channel=ref["channel"], timestamp=ref["ts"], name=emoji_name
                )
            except Exception as e:
                logger.debug(f"Could not add Slack reaction {emoji_name}: {e}")

        async def _unreact(ref, emoji):
            emoji_name = {
                "📨": "incoming_envelope",
                "🤔": "thinking_face",
                "⚙️": "gear",
                "✅": "white_check_mark",
                "❌": "x",
                "💬": "speech_balloon",
            }.get(emoji, "robot_face")
            try:
                await self._app.client.reactions_remove(
                    channel=ref["channel"], timestamp=ref["ts"], name=emoji_name
                )
            except Exception as e:
                logger.debug(f"Could not remove Slack reaction: {e}")

        tracker = LifecycleTracker(
            channel_id="slack",
            message_ref=msg_ref,
            react_fn=_react,
            unreact_fn=_unreact,
        )

        channel_msg = ChannelMessage(
            channel_id="slack",
            sender_id=user,
            sender_name=user,  # Could be enriched via users.info API
            content=text,
            metadata={
                "channel": channel,
                "channel_type": channel_type,
                "ts": ts,
                "is_dm": channel_type == "im",
                "lifecycle_tracker": tracker,
                "model_override": get_model_override("slack"),
            },
        )

        await tracker.phase("queued")

        try:
            await tracker.phase("thinking")
            await self._dispatch_message(channel_msg)
            await tracker.done()
        except Exception as e:
            await tracker.error()
            logger.error(f"Error handling Slack message: {e}")
            raise

    async def send_message(self, to: str, content: str,
                           attachments: Optional[List[str]] = None,
                           **kwargs) -> bool:
        """
        Send a message to a Slack target.

        'to' format: "channel:<channel_id>"
        """
        if not self._app:
            logger.error("Slack client not connected")
            return False

        try:
            _, channel_id = to.split(":", 1)
        except (ValueError, AttributeError):
            logger.error(f"Invalid 'to' format: {to}. Use 'channel:<channel_id>'")
            return False

        # OpenClaw #22359: Retry on overload with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            try:
                chunks = self._split_message(content, max_length=4000)
                for chunk in chunks:
                    await self._app.client.chat_postMessage(channel=channel_id, text=chunk)
                return True
            except Exception as e:
                if _is_overload_error(e) and attempt < self.MAX_RETRIES - 1:
                    wait_time = self.BASE_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Slack API overloaded (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to send Slack message: {e}")
                    return False
        return False

    @staticmethod
    def _split_message(content: str, max_length: int = 4000) -> List[str]:
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
